"""
Per-slot dosing marks read off a prescription's timing columns.

A printed prescription usually says *when* to take a medicine in a table with
one column per slot, not just how many times a day.  The stated frequency
("Twice Daily") cannot distinguish Morning+Afternoon from Morning+Night, so the
slot marks have to survive extraction rather than being re-derived from a
default table.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .frequency_reminder_rules import required_reminder_count
from .medication_constants import MedicationFrequency, normalize_frequency

# Day order — response and reminder lists are emitted in this sequence.
SLOT_LABELS: Tuple[str, ...] = ("Morning", "Afternoon", "Evening", "Night")

_SLOT_KEYS: Tuple[str, ...] = tuple(label.lower() for label in SLOT_LABELS)

# Values a model may emit for an unmarked cell ("-", blank, 0).
_UNMARKED_TEXT = {"", "-", "--", "–", "—", "0", "no", "false", "nil", "none", "n/a"}

_DAILY_FREQUENCIES = {
    MedicationFrequency.ONCE_DAILY.value,
    MedicationFrequency.TWICE_DAILY.value,
    MedicationFrequency.THREE_TIMES_DAILY.value,
    MedicationFrequency.FOUR_TIMES_DAILY.value,
}

_COUNT_TO_FREQUENCY = {
    1: MedicationFrequency.ONCE_DAILY.value,
    2: MedicationFrequency.TWICE_DAILY.value,
    3: MedicationFrequency.THREE_TIMES_DAILY.value,
    4: MedicationFrequency.FOUR_TIMES_DAILY.value,
}

# JSON-schema fragment for the `timing` object on an extracted medicine.
TIMING_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {key: {"type": "boolean"} for key in _SLOT_KEYS},
    "required": list(_SLOT_KEYS),
}

# Appended to extraction prompts so the model fills `timing` from the columns.
TIMING_PROMPT = (
    "Prescriptions often carry a dose-timing table with one column per slot "
    "(Morning, Afternoon, Evening, Night — sometimes printed as Noon or Bedtime, "
    "and sometimes qualified as 'After Food'). For each medicine set the matching "
    "timing flag to true only where that row's column holds a dose: a count such "
    "as 1, a tick, or 'Yes'. A dash, a blank cell, or 0 means false. When the "
    "document gives only a worded frequency and has no per-slot columns, set every "
    "timing flag to false."
)

_FORM_ONLY_DOSAGE = {
    "tablet",
    "tablets",
    "capsule",
    "capsules",
    "syrup",
    "liquid",
    "injection",
    "inhaler",
    "drops",
    "drop",
    "cream",
    "ointment",
    "gel",
    "patch",
    "suppository",
    "powder",
}

_GENERIC_INSTRUCTIONS = {
    "kindly take medications as advised",
    "take medications as advised",
    "take as advised",
    "as advised",
    "for any queries, contact the clinic",
}

_SCHEDULE_HINT = re.compile(
    r"\b("
    r"once|twice|thrice|three times|four times|daily|weekly|monthly|"
    r"bd|tds|qid|od|every other|after food|before food|at bedtime|"
    r"morning|afternoon|evening|night|prn|sos"
    r")\b",
    re.IGNORECASE,
)

_QUANTITY_HINT = re.compile(r"\b\d+\s*(tab|tablet|cap|capsule|ml|mg|g|iu|drop|puff)\b", re.IGNORECASE)


def _is_marked(value: Any) -> bool:
    """True when a timing cell carries a dose."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() not in _UNMARKED_TEXT
    return False


def _clean_text(value: Any) -> str:
    text = (value or "").strip()
    return "" if text.lower() == "uncertain" else text


def _is_form_only_dosage(value: str) -> bool:
    """True when dosage is only a medicine form such as 'Tablet', not a quantity."""
    return value.strip().lower() in _FORM_ONLY_DOSAGE


def _schedule_hint_in_text(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if text.lower() in _GENERIC_INSTRUCTIONS:
        return False
    return bool(_SCHEDULE_HINT.search(text) or _QUANTITY_HINT.search(text))


def document_states_schedule(medicine: Dict[str, Any]) -> bool:
    """
    True when the extraction carries schedule evidence from the document.

    A list-style prescription that only names medicines and strengths does not
    state how often or when to take them. In that case an inferred frequency or
    default Morning slot would be invented, so the caller should leave schedule
    fields blank for manual entry.
    """
    if slots_from_timing(medicine.get("timing")):
        return True

    dosage = _clean_text(medicine.get("dosage"))
    if dosage and not _is_form_only_dosage(dosage):
        return True

    instructions = _clean_text(medicine.get("instructions"))
    if instructions and _schedule_hint_in_text(instructions):
        return True
    return False


def clear_unsupported_schedule(medicine: Dict[str, Any]) -> Dict[str, Any]:
    """Drop frequency the document never supported; keep name/strength intact."""
    if document_states_schedule(medicine):
        return medicine
    medicine["frequency"] = ""
    if "reminders" in medicine:
        medicine["reminders"] = []
    timing = medicine.get("timing")
    if isinstance(timing, dict):
        medicine["timing"] = {key: False for key in _SLOT_KEYS}
    return medicine


def slots_from_timing(timing: Any) -> List[str]:
    """Canonical labels for the marked slots, in day order."""
    if not isinstance(timing, dict):
        return []
    return [
        label
        for label, key in zip(SLOT_LABELS, _SLOT_KEYS)
        if _is_marked(timing.get(key))
    ]


def frequency_for_slot_count(count: int) -> Optional[str]:
    """Daily frequency implied by a slot count, or None beyond four slots."""
    return _COUNT_TO_FREQUENCY.get(count)


# Slots to assume when a frequency states how many doses but not when to take
# them. Kept in step with MedicationScheduleService.FREQUENCY_DEFAULTS, which
# holds the same schedule as clock times; a test pins the two together.
_DEFAULT_SLOTS: Dict[str, List[str]] = {
    MedicationFrequency.ONCE_DAILY.value: ["Morning"],
    MedicationFrequency.TWICE_DAILY.value: ["Morning", "Night"],
    MedicationFrequency.THREE_TIMES_DAILY.value: ["Morning", "Afternoon", "Night"],
    MedicationFrequency.FOUR_TIMES_DAILY.value: [
        "Morning", "Afternoon", "Evening", "Night",
    ],
    MedicationFrequency.EVERY_OTHER_DAY.value: ["Morning"],
    MedicationFrequency.ONCE_WEEKLY.value: ["Morning"],
    MedicationFrequency.ONCE_MONTHLY.value: ["Morning"],
}


def default_slots_for_frequency(frequency: Optional[str]) -> List[str]:
    """
    Usual slots for a stated frequency; empty when it constrains nothing.

    PRN, a blank frequency and unrecognised wordings all return no slots — there
    is no dose count to satisfy, so picking a time would be inventing one.
    """
    if not (frequency or "").strip():
        return []
    return list(_DEFAULT_SLOTS.get(normalize_frequency(frequency), []))


def reconcile_frequency_with_slots(
    frequency: str, slots: List[str]
) -> Tuple[str, List[str]]:
    """
    Reconcile a worded frequency against the slot marks.

    The marks are the stronger signal — they were read off the document — so a
    daily frequency that disagrees with them is corrected.  Non-daily
    frequencies (weekly, monthly) keep their wording and surrender the extra
    slots instead.  The result always satisfies
    `validate_reminders_match_frequency`, which rejects a save when the reminder
    count does not match the frequency.
    """
    stated = (frequency or "").strip()

    if not slots:
        # Nothing marks when to take it. With no stated frequency either, there
        # is no schedule on the document to honour, so it is PRN.
        if not stated:
            return MedicationFrequency.AS_NEEDED.value, []
        # Reported as-is: only extraction may supply defaults, since an empty
        # list on save means the user cleared it.
        return normalize_frequency(stated), []

    if not stated:
        # The marks are the only schedule available; let them set the frequency.
        derived = frequency_for_slot_count(len(slots))
        if derived:
            return derived, slots

    canonical = normalize_frequency(stated)
    required = required_reminder_count(canonical)

    if required == len(slots):
        return canonical, slots

    if canonical in _DAILY_FREQUENCIES:
        derived = frequency_for_slot_count(len(slots))
        if derived:
            return derived, slots

    if required:
        return canonical, slots[:required]
    return canonical, slots


def apply_medicine_reminders(extracted: Any) -> Any:
    """
    Replace each medicine's `timing` booleans with a `reminders` label list, and
    settle the frequency against those slots.

    The model answers per column because that mirrors the printed table, but
    callers only need the slots that carry a dose, under the same `reminders`
    name the medication API already uses.  Reconciling here keeps the preview
    payload showing the frequency the save will store, rather than the blank the
    model returns when the document only marks columns.
    """
    if not isinstance(extracted, dict):
        return extracted
    for key in ("medicines", "medications"):
        for medicine in extracted.get(key) or []:
            if not isinstance(medicine, dict):
                continue
            medicine = clear_unsupported_schedule(medicine)
            slots = slots_from_timing(medicine.pop("timing", None))
            frequency, slots = reconcile_frequency_with_slots(
                (medicine.get("frequency") or "").strip(), slots
            )
            medicine["frequency"] = frequency
            medicine["reminders"] = slots
    return extracted
