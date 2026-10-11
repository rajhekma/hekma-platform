import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ...config.medication_dose_config import get_medication_dose_config
from ...repositories.compliance_repo import (
    count_brand_name_medications,
    count_total_medications,
    get_active_medications_with_reminders,
    get_history_in_range,
    get_patients_by_ids,
)
from ...utils.compliance_eligibility import (
    compliance_day_bounds,
    medication_effective_bounds,
    slot_counts_for_compliance,
)
from ...utils.compliance_history import (
    find_history_entry_for_today_slot,
    index_history,
    last_taken_in_period,
    taken_timestamp,
)
from ...utils.dose_status import compliance_status_for_slot
from ...utils.patient_timezone import resolve_timezone_for_patient
from ...utils.reminder_resolver import (
    dose_slot_name,
    resolve_reminder,
    scheduled_time_ms,
)

_TAKEN = frozenset({"taken", "Taken"})
_MISSED = frozenset({"missed", "Missed"})
_SKIPPED = frozenset({"skipped", "Skipped"})

PERIOD_DAYS = {
    "7d": 7,
    "1m": 30,
    "6m": 180,
    "1y": 365,
}

SHIFT_ORDER = tuple(slot.name for slot in get_medication_dose_config().slots)


def _epoch_ms(day: date, hour: int, minute: int, tz: ZoneInfo) -> int:
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
    return int(dt.timestamp() * 1000)


def _day_end_ms(day: date, tz: ZoneInfo) -> int:
    dt = datetime(day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=tz)
    return int(dt.timestamp() * 1000)


def _period_bounds_ms(start_day: date, end_day: date, tz: ZoneInfo) -> tuple[int, int]:
    start_ms = _epoch_ms(start_day, 0, 0, tz)
    end_ms = _day_end_ms(end_day, tz)
    return start_ms, end_ms


def _shift_bucket(
    label: Optional[str],
    scheduled_time: Optional[int] = None,
    tz: Optional[ZoneInfo] = None,
) -> str:
    """Map reminder labels or local times into configured dose slots."""
    return dose_slot_name(label, scheduled_time, tz)


def _patient_display_name(patient_id: str, patient_row: Optional[Dict]) -> str:
    if not patient_row:
        return patient_id
    given = (patient_row.get("given_name") or "").strip()
    family = (patient_row.get("family_name") or "").strip()
    full = f"{given} {family}".strip()
    return full or patient_id


def _medication_display(med: Dict) -> str:
    strength = (med.get("strength") or "").strip()
    name = (med.get("name") or "").strip()
    if not name:
        return (med.get("dosage") or "").strip() or "Medication"
    # Scanned prescriptions often write the strength into the name as well, so
    # appending it unconditionally yields "Paracetamol 650 mg 650 mg".
    if strength and strength.lower() not in name.lower():
        return f"{name} {strength}"
    return name


class MedicationComplianceService:
    """Cohort-level medication adherence analytics for the compliance dashboard."""

    def get_dashboard(
        self,
        period: str = "7d",
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        timezone_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        days = PERIOD_DAYS.get(period, 7)
        tz = resolve_timezone_for_patient(None, timezone_name)
        today = datetime.now(tz).date()
        period_start = today - timedelta(days=days - 1)
        prev_start = period_start - timedelta(days=days)
        prev_end = period_start - timedelta(days=1)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        pad_ms = 24 * 60 * 60 * 1000
        range_from_ms = _epoch_ms(prev_start, 0, 0, tz) - pad_ms
        range_to_ms = _day_end_ms(today, tz) + pad_ms

        all_medications = self._group_medications(get_active_medications_with_reminders())
        history_rows = get_history_in_range(range_from_ms, range_to_ms)
        history_exact, history_by_med = index_history(history_rows)

        # Names are needed to match the search term, so resolve the full cohort first.
        patients_map = get_patients_by_ids(
            list({m["patient_id"] for m in all_medications.values()})
        )

        # Narrow before any statistics run: the summary has to describe the same
        # cohort as the table, not the whole dashboard.
        medications = self._filter_medications(all_medications, patients_map, search)
        patient_ids = list({m["patient_id"] for m in medications.values()})

        period_stats = self._analyze_range(
            medications,
            history_exact,
            history_by_med,
            period_start,
            today,
            now_ms,
            tz,
        )
        previous_stats = self._analyze_range(
            medications,
            history_exact,
            history_by_med,
            prev_start,
            prev_end,
            _day_end_ms(prev_end, tz),
            tz,
        )

        today_stats = self._analyze_range(
            medications,
            history_exact,
            history_by_med,
            today,
            today,
            now_ms,
            tz,
        )

        # Fixed rolling 7-day window for the "this week" summary card — independent
        # of the selected period filter (1m / 6m / 1y still show last-7-day missed).
        week_start = today - timedelta(days=6)
        week_stats = self._analyze_range(
            medications,
            history_exact,
            history_by_med,
            week_start,
            today,
            now_ms,
            tz,
        )

        overall = period_stats["compliance_rate"]
        prev_overall = previous_stats["compliance_rate"]
        # Either side may be undefined (nothing due), which makes a delta meaningless.
        change = (
            round(overall - prev_overall, 1)
            if overall is not None and prev_overall is not None
            else 0.0
        )

        table_rows = self._build_patient_rows(
            medications, period_stats["medication_stats"], patients_map
        )
        # Summary, trend and shifts all describe the same cohort, so the headline
        # number stays reproducible from the graph beneath it.
        missed_by_shift = period_stats["missed_by_shift"]
        trend = self._build_trend(
            medications, history_exact, history_by_med, period_start, today, now_ms, tz
        )

        # Worst adherence first; medications with nothing due yet sort last.
        table_rows.sort(
            key=lambda r: (
                r["compliancePercentage"] is None,
                r["compliancePercentage"] if r["compliancePercentage"] is not None else 0.0,
            )
        )
        total_rows = len(table_rows)
        page = max(1, page)
        limit = max(1, min(limit, 100))
        start = (page - 1) * limit
        paged = table_rows[start : start + limit]

        return {
            "period": period,
            "summary": {
                "overallCompliancePercentage": overall,
                "complianceChangeVsPreviousPeriod": change,
                "totalActivePatients": len(patient_ids),
                "missedDosesToday": today_stats["missed_count"],
                "totalMissedDosesThisWeek": week_stats["missed_count"],
                "totalMissedDosesInPeriod": period_stats["missed_count"],
                "activeDosage": period_stats["active_dosage"],
                "activeMedicationsCount": len(medications),
                # Both counts follow the table: scoped to the search, else global.
                "totalMedicationsCount": (
                    len(medications) if search else count_total_medications()
                ),
                "brandNameMedicationsCount": (
                    self._count_brand_name(medications)
                    if search
                    else count_brand_name_medications()
                ),
            },
            "complianceTrend": trend,
            "missedDosesByShift": missed_by_shift,
            "patients": {
                "total": total_rows,
                "page": page,
                "limit": limit,
                "entries": paged,
            },
        }

    @staticmethod
    def _filter_medications(
        medications: Dict[int, Dict],
        patients_map: Dict[str, Dict],
        search: Optional[str],
    ) -> Dict[int, Dict]:
        """Medications matching the search term by patient id, name, or drug."""
        term = (search or "").strip().lower()
        if not term:
            return medications

        matched: Dict[int, Dict] = {}
        for med_id, med in medications.items():
            patient_id = str(med["patient_id"])
            patient_name = _patient_display_name(patient_id, patients_map.get(patient_id))
            if (
                term in patient_id.lower()
                or term in patient_name.lower()
                or term in _medication_display(med).lower()
            ):
                matched[med_id] = med
        return matched

    @staticmethod
    def _count_brand_name(medications: Dict[int, Dict]) -> int:
        """Brand-name heuristic applied to the scoped cohort, matching the SQL regex."""
        pattern = re.compile(r"[A-Z][a-z]+ [A-Z]")
        return sum(
            1 for med in medications.values() if pattern.search(str(med.get("name") or ""))
        )

    @staticmethod
    def _group_medications(rows: List[Dict]) -> Dict[int, Dict]:
        meds: Dict[int, Dict] = {}
        for row in rows:
            mid = row["medication_id"]
            if mid not in meds:
                meds[mid] = {
                    "medication_id": mid,
                    "patient_id": row["patient_id"],
                    "name": row["name"],
                    "strength": row.get("strength") or "",
                    "dosage": row.get("dosage") or "",
                    "how_much_to_take": row.get("how_much_to_take") or "",
                    "frequency": row.get("frequency") or "",
                    "start_date": row.get("start_date"),
                    "end_date": row.get("end_date"),
                    "created_at": row.get("created_at"),
                    "daily_target_count": row.get("daily_target_count"),
                    # Absent column (older rows / fixtures) means reminders are on.
                    "is_reminder_enabled": row.get("is_reminder_enabled", True),
                    "reminders": [],
                }
            if row.get("reminder_id") is not None:
                meds[mid]["reminders"].append(
                    {
                        "id": row["reminder_id"],
                        "hour": row["hour"],
                        "minute": row["minute"],
                        "label": row.get("label"),
                    }
                )
        return meds

    def _analyze_range(
        self,
        medications: Dict[int, Dict],
        history_exact: Dict,
        history_by_med: Dict[int, List[Dict]],
        start_day: date,
        end_day: date,
        cutoff_ms: int,
        tz: ZoneInfo,
    ) -> Dict[str, Any]:
        taken = missed = skipped = pending = due = active_dosage = 0
        missed_by_shift: Dict[str, int] = {s: 0 for s in SHIFT_ORDER}
        med_stats: Dict[int, Dict[str, Any]] = {}
        period_start_ms, period_end_ms = _period_bounds_ms(start_day, end_day, tz)

        for med_id, med in medications.items():
            # Count-based meds are tracked via daily-count APIs, not slot compliance.
            if med.get("daily_target_count"):
                continue

            med_taken = med_missed = med_skipped = med_pending = med_due = med_active_dosage = 0
            last_taken_time: Optional[int] = None
            last_taken_label: Optional[str] = None

            # Match TodayMedicationService: all active slot meds count toward
            # adherence, regardless of is_reminder_enabled. Meds without stored
            # reminders still get a default Morning slot for the day.
            slots = med.get("reminders") or []
            if not slots:
                slots = [{"id": None, "label": "Morning"}]
            reminder_labels = {
                reminder["id"]: reminder.get("label")
                for reminder in slots
                if reminder.get("id") is not None
            }
            effective_start_ms, effective_end_ms = medication_effective_bounds(med, tz)
            loop_start, loop_end = compliance_day_bounds(med, start_day, end_day, tz)

            day = loop_start
            while day <= loop_end:
                # Whether a slot counts as due on this day (respects end-of-day / partial today).
                due_cutoff = min(cutoff_ms, _day_end_ms(day, tz))
                # One dose log may only satisfy one slot. Slots sit closer together
                # than the history match tolerance, so without this a single log
                # marks every slot of the day taken.
                used_entry_keys: set = set()
                for reminder in slots:
                    scheduled = scheduled_time_ms(day, resolve_reminder(reminder), tz)
                    if not slot_counts_for_compliance(
                        scheduled, effective_start_ms, effective_end_ms
                    ):
                        continue

                    # All scheduled slots in the period window, including slots
                    # later today that are not yet due.
                    active_dosage += 1
                    med_active_dosage += 1

                    if scheduled > due_cutoff:
                        continue

                    due += 1
                    med_due += 1
                    entry = find_history_entry_for_today_slot(
                        med_id,
                        scheduled,
                        reminder.get("id"),
                        history_exact,
                        history_by_med,
                        used_entry_keys,
                    )
                    if entry:
                        used_entry_keys.add(
                            (entry["medication_id"], int(entry["scheduled_time"]))
                        )
                    # Unlogged doses become missed when the display slot ends
                    # (logging may still be allowed within the 24h edit window).
                    status = self._status_from_entry(entry, scheduled, cutoff_ms, tz)

                    if status in _TAKEN:
                        taken += 1
                        med_taken += 1
                        taken_at = taken_timestamp(entry, scheduled)
                        if taken_at and (last_taken_time is None or taken_at > last_taken_time):
                            last_taken_time = taken_at
                            last_taken_label = reminder.get("label")
                    elif status in _MISSED:
                        missed += 1
                        med_missed += 1
                        shift = _shift_bucket(reminder.get("label"), scheduled, tz)
                        missed_by_shift[shift] = missed_by_shift.get(shift, 0) + 1
                    elif status in _SKIPPED:
                        skipped += 1
                        med_skipped += 1
                    else:
                        # Slot has arrived but is still open — not late yet.
                        pending += 1
                        med_pending += 1

                day += timedelta(days=1)

            history_last_time, history_last_label = last_taken_in_period(
                history_by_med,
                med_id,
                period_start_ms,
                period_end_ms,
                reminder_labels,
            )
            if history_last_time and (
                last_taken_time is None or history_last_time > last_taken_time
            ):
                last_taken_time = history_last_time
                last_taken_label = history_last_label or last_taken_label

            # Only resolved slots can score: a dose still inside its open window
            # has not been missed, so it must not drag the rate down.
            med_resolved = med_due - med_pending
            med_stats[med_id] = {
                "taken": med_taken,
                "missed": med_missed,
                "skipped": med_skipped,
                "pending": med_pending,
                "due": med_due,
                "activeDosage": med_active_dosage,
                # Nothing resolved yet -> adherence is undefined, not perfect.
                "compliance_rate": (
                    round((med_taken / med_resolved) * 100, 1) if med_resolved else None
                ),
                "lastTakenTime": last_taken_time,
                "lastTakenLabel": last_taken_label,
            }

        resolved = due - pending
        compliance_rate = round((taken / resolved) * 100, 1) if resolved else None
        ordered_shifts = {k: missed_by_shift.get(k, 0) for k in SHIFT_ORDER}

        return {
            "taken": taken,
            "missed": missed,
            "skipped": skipped,
            "pending": pending,
            "due": due,
            "active_dosage": active_dosage,
            "missed_count": missed,
            "compliance_rate": compliance_rate,
            "missed_by_shift": ordered_shifts,
            "medication_stats": med_stats,
        }

    @staticmethod
    def _status_from_entry(
        entry: Optional[Dict],
        scheduled_time: int,
        cutoff_ms: int,
        tz: ZoneInfo,
    ) -> str:
        """Resolve stored or calculated status in the dashboard timezone."""
        return compliance_status_for_slot(entry, scheduled_time, cutoff_ms, tz)

    def _build_trend(
        self,
        medications: Dict[int, Dict],
        history_exact: Dict,
        history_by_med: Dict[int, List[Dict]],
        start_day: date,
        end_day: date,
        now_ms: int,
        tz: ZoneInfo,
    ) -> List[Dict[str, Any]]:
        points = []
        day = start_day
        while day <= end_day:
            stats = self._analyze_range(
                medications,
                history_exact,
                history_by_med,
                day,
                day,
                now_ms,
                tz,
            )
            points.append(
                {
                    "date": day.isoformat(),
                    "compliancePercentage": stats["compliance_rate"],
                    "takenCount": stats["taken"],
                    "missedCount": stats["missed"],
                    "skippedCount": stats["skipped"],
                    "pendingCount": stats["pending"],
                    "dueCount": stats["due"],
                }
            )
            day += timedelta(days=1)
        return points

    def _build_patient_rows(
        self,
        medications: Dict[int, Dict],
        med_stats: Dict[int, Dict[str, Any]],
        patients_map: Dict[str, Dict],
    ) -> List[Dict[str, Any]]:
        rows = []
        for med_id, med in medications.items():
            stats = med_stats.get(med_id, {})
            patient_id = med["patient_id"]
            rows.append(
                {
                    "patientId": patient_id,
                    "patientName": _patient_display_name(patient_id, patients_map.get(patient_id)),
                    "medicationId": med_id,
                    "medicationDisplay": _medication_display(med),
                    "compliancePercentage": stats.get("compliance_rate"),
                    "missedDoses": stats.get("missed", 0),
                    "dosesDue": stats.get("due", 0),
                    "dosesTaken": stats.get("taken", 0),
                    "dosesSkipped": stats.get("skipped", 0),
                    "dosesPending": stats.get("pending", 0),
                    "activeDosage": stats.get("activeDosage", 0),
                    "lastDoseTaken": {
                        "takenTime": stats.get("lastTakenTime"),
                        "label": stats.get("lastTakenLabel"),
                    },
                }
            )
        return rows
