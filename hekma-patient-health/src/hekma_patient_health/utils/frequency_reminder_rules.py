"""Rules that tie fixed daily frequencies to an exact reminder-slot count."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from .medication_constants import MedicationFrequency, normalize_frequency

# Frequencies that require an exact number of reminder slots on save.
_REQUIRED_SLOT_COUNTS = {
    MedicationFrequency.ONCE_DAILY.value: 1,
    MedicationFrequency.TWICE_DAILY.value: 2,
    MedicationFrequency.THREE_TIMES_DAILY.value: 3,
    MedicationFrequency.FOUR_TIMES_DAILY.value: 4,
    MedicationFrequency.EVERY_OTHER_DAY.value: 1,
    MedicationFrequency.ONCE_WEEKLY.value: 1,
    MedicationFrequency.ONCE_MONTHLY.value: 1,
}


def required_reminder_count(frequency: Optional[str]) -> Optional[int]:
    """Return required slot count for a fixed frequency, or None when unconstrained."""
    if not frequency:
        return None
    return _REQUIRED_SLOT_COUNTS.get(normalize_frequency(frequency))


def validate_reminders_match_frequency(
    frequency: Optional[str],
    reminders: Sequence[Any],
    *,
    daily_target_count: Optional[int] = None,
) -> None:
    """
    Require exact reminder count for fixed daily frequencies.

    A stated frequency is a promise about how many doses a day, so it has to be
    matched by that many slots — Once Daily needs 1, Twice Daily needs 2, and so
    on — otherwise the medication is saved with a schedule that never fires.

    Nothing is required when the frequency is unconstrained: blank (the document
    never said), As Needed (PRN), or a wording outside the fixed set. Count-based
    meds (dailyTargetCount set) skip the check too. Raises ValueError when a
    constrained frequency does not get its exact slot count.
    """
    if daily_target_count:
        return

    required = required_reminder_count(frequency)
    if required is None:
        return

    actual = len(list(reminders or []))
    if actual == required:
        return

    canonical = normalize_frequency(frequency)
    raise ValueError(
        f"{canonical} requires exactly {required} reminder slot(s); "
        f"got {actual}."
    )
