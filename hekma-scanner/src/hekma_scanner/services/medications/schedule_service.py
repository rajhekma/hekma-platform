import re
from typing import Any, Dict, List, Optional

from ...utils.medication_constants import normalize_frequency
from ...utils.reminder_resolver import LABEL_TIMES, resolve_reminder, resolve_reminders


def _slot(label_key: str) -> Dict:
    hour, minute = LABEL_TIMES[label_key]
    from ...utils.reminder_resolver import CANONICAL_LABELS

    return {"hour": hour, "minute": minute, "label": CANONICAL_LABELS[label_key]}


class MedicationScheduleService:
    """Maps medication frequency strings and reminder labels to schedules."""

    FREQUENCY_DEFAULTS: Dict[str, List[Dict]] = {
        "once daily": [_slot("morning")],
        "twice daily": [_slot("morning"), _slot("night")],
        "three times daily": [_slot("morning"), _slot("afternoon"), _slot("night")],
        "3 times daily": [_slot("morning"), _slot("afternoon"), _slot("night")],
        "four times daily": [
            _slot("morning"),
            _slot("afternoon"),
            _slot("evening"),
            _slot("night"),
        ],
        "4 times daily": [
            _slot("morning"),
            _slot("afternoon"),
            _slot("evening"),
            _slot("night"),
        ],
        "every other day": [_slot("morning")],
        "once weekly": [_slot("morning")],
        "once monthly": [_slot("morning")],
        # PRN is taken on demand, so there is no slot to schedule.
        "as needed (prn)": [],
        # legacy
        "every 6 hours": [
            {"hour": 6, "minute": 0},
            {"hour": 12, "minute": 0},
            {"hour": 18, "minute": 0},
            {"hour": 0, "minute": 0},
        ],
        "every 4 hours": [
            {"hour": 6, "minute": 0},
            {"hour": 10, "minute": 0},
            {"hour": 14, "minute": 0},
            {"hour": 18, "minute": 0},
            {"hour": 22, "minute": 0},
            {"hour": 2, "minute": 0},
        ],
        "morning & night": [_slot("morning"), _slot("night")],
        "morning, afternoon & night": [_slot("morning"), _slot("afternoon"), _slot("night")],
    }

    def build(
        self,
        frequency: str,
        explicit_reminders: Optional[List[Any]] = None,
        use_frequency_defaults: bool = True,
    ) -> List[Dict]:
        if explicit_reminders:
            return resolve_reminders(explicit_reminders)
        if use_frequency_defaults:
            return self.from_frequency(frequency)
        return []

    def from_frequency(self, frequency: str) -> List[Dict]:
        # No stated frequency means no dose count to schedule against.
        # normalize_frequency would otherwise read blank as Once Daily and
        # invent a Morning slot the prescription never asked for.
        if not (frequency or "").strip():
            return []
        canonical = normalize_frequency(frequency)
        normalized = re.sub(r"\s+", " ", canonical.strip().lower())
        if normalized in self.FREQUENCY_DEFAULTS:
            return self.FREQUENCY_DEFAULTS[normalized]

        every_hours = re.match(r"every (\d+) hours?", normalized)
        if every_hours:
            interval = int(every_hours.group(1))
            if interval <= 0 or interval > 24:
                return self.FREQUENCY_DEFAULTS["once daily"]
            reminders = []
            hour = 6
            while hour < 24:
                reminders.append({"hour": hour, "minute": 0})
                hour += interval
            return reminders or self.FREQUENCY_DEFAULTS["once daily"]

        return self.FREQUENCY_DEFAULTS["once daily"]

    @staticmethod
    def from_labels(labels: List[Any]) -> List[Dict]:
        return resolve_reminders(labels)

    @staticmethod
    def resolve_reminder(reminder: Dict[str, Any]) -> Dict[str, Any]:
        return resolve_reminder(reminder)
