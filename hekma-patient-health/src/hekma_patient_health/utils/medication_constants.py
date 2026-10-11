import re
from enum import Enum
from typing import Dict, Optional


class MedicationType(str, Enum):
    TABLET = "Tablet"
    CAPSULE = "Capsule"
    LIQUID = "Liquid"
    INJECTION = "Injection"
    INFUSION_IV = "Infusion (IV)"
    INHALER = "Inhaler"
    NASAL_SPRAY = "Nasal Spray"
    EYE_DROPS = "Eye Drops"
    EAR_DROPS = "Ear Drops"
    CREAM = "Cream"
    OINTMENT = "Ointment"
    GEL = "Gel"
    PATCH = "Patch"
    SUPPOSITORY = "Suppository"
    POWDER = "Powder"
    OTHER = "Other"


class MedicationFrequency(str, Enum):
    ONCE_DAILY = "Once Daily"
    TWICE_DAILY = "Twice Daily"
    THREE_TIMES_DAILY = "Three Times Daily"
    FOUR_TIMES_DAILY = "Four Times Daily"
    EVERY_OTHER_DAY = "Every other day"
    ONCE_WEEKLY = "Once Weekly"
    ONCE_MONTHLY = "Once Monthly"
    AS_NEEDED = "As Needed (PRN)"


# Legacy / AI aliases -> canonical frequency enum value
FREQUENCY_ALIASES: Dict[str, MedicationFrequency] = {
    "once daily": MedicationFrequency.ONCE_DAILY,
    "twice daily": MedicationFrequency.TWICE_DAILY,
    "3 times daily": MedicationFrequency.THREE_TIMES_DAILY,
    "three times daily": MedicationFrequency.THREE_TIMES_DAILY,
    "4 times daily": MedicationFrequency.FOUR_TIMES_DAILY,
    "four times daily": MedicationFrequency.FOUR_TIMES_DAILY,
    "every other day": MedicationFrequency.EVERY_OTHER_DAY,
    "once weekly": MedicationFrequency.ONCE_WEEKLY,
    "once monthly": MedicationFrequency.ONCE_MONTHLY,
    # PRN wordings seen on prescriptions; all mean "no fixed schedule".
    "as needed": MedicationFrequency.AS_NEEDED,
    "as needed (prn)": MedicationFrequency.AS_NEEDED,
    "prn": MedicationFrequency.AS_NEEDED,
    "sos": MedicationFrequency.AS_NEEDED,
    "when required": MedicationFrequency.AS_NEEDED,
    "as required": MedicationFrequency.AS_NEEDED,
    "if required": MedicationFrequency.AS_NEEDED,
    "if needed": MedicationFrequency.AS_NEEDED,
    # Mobile toggles PRN separately from the frequency picker.
    "asneeded": MedicationFrequency.AS_NEEDED,
    # legacy schedule strings still accepted
    "every 6 hours": MedicationFrequency.ONCE_DAILY,
    "every 4 hours": MedicationFrequency.FOUR_TIMES_DAILY,
    "morning & night": MedicationFrequency.TWICE_DAILY,
    "morning, afternoon & night": MedicationFrequency.THREE_TIMES_DAILY,
}

MEDICATION_TYPE_ALIASES: Dict[str, MedicationType] = {
    "syrup": MedicationType.LIQUID,
    "drops": MedicationType.EYE_DROPS,
    # Clients name this one without the parenthesised route.
    "infusion": MedicationType.INFUSION_IV,
    "iv": MedicationType.INFUSION_IV,
    "iv infusion": MedicationType.INFUSION_IV,
}


def _squash(value: str) -> str:
    """
    Fold casing and punctuation away so client and server spellings meet.

    Mobile clients send enum case names ("nasalSpray", "onceDaily") while the
    API and AI use display text ("Nasal Spray", "Once Daily"); both reduce to
    the same key, as do "Infusion IV" and "Infusion (IV)".
    """
    return re.sub(r"[^a-z0-9]", "", value.lower())


_FREQUENCY_BY_KEY: Dict[str, MedicationFrequency] = {
    _squash(freq.value): freq for freq in MedicationFrequency
}
_FREQUENCY_BY_KEY.update({_squash(k): v for k, v in FREQUENCY_ALIASES.items()})

_TYPE_BY_KEY: Dict[str, MedicationType] = {
    _squash(med_type.value): med_type for med_type in MedicationType
}
_TYPE_BY_KEY.update({_squash(k): v for k, v in MEDICATION_TYPE_ALIASES.items()})


def normalize_frequency(value: Optional[str]) -> str:
    """
    Map client / OCR wording to a canonical frequency label.

    Blank means the document or caller stated no frequency — never default to
    Once Daily here; scan and save paths infer PRN or leave the field empty.
    """
    if not value or not str(value).strip():
        return ""
    match = _FREQUENCY_BY_KEY.get(_squash(str(value)))
    return match.value if match else str(value).strip()


def normalize_medication_type(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, MedicationType):
        return value.value
    raw = str(value).strip()
    if not raw:
        return None
    match = _TYPE_BY_KEY.get(_squash(raw))
    return match.value if match else raw
