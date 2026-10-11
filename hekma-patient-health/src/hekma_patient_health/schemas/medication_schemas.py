from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from ..utils.medication_constants import (
    MedicationFrequency,
    MedicationType,
    normalize_frequency,
    normalize_medication_type,
)
from ..utils.medication_payload import apply_as_needed_schedule, normalize_medication_payload
from ..utils.reminder_resolver import coerce_reminder_entries, resolve_reminder


class ReminderLabel(str, Enum):
    EARLY_MORNING = "Early Morning"
    MORNING = "Morning"
    NOON = "Noon"
    AFTERNOON = "Afternoon"
    EVENING = "Evening"
    NIGHT = "Night"


class ReminderInput(BaseModel):
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    minute: Optional[int] = Field(default=None, ge=0, le=59)
    label: Optional[Union[ReminderLabel, str]] = None

    @model_validator(mode="after")
    def resolve_from_label(self):
        resolved = resolve_reminder(self.model_dump())
        self.hour = resolved["hour"]
        self.minute = resolved["minute"]
        self.label = resolved["label"]
        return self


def _merge_reminder_fields(data: Any) -> Any:
    if not isinstance(data, dict):
        return data

    merged = apply_as_needed_schedule(dict(data))
    label_list = merged.get("reminderLabels")
    reminders = merged.get("reminders")

    if label_list and not reminders:
        merged["reminders"] = [{"label": label} for label in label_list]
    elif isinstance(reminders, list) and reminders and isinstance(reminders[0], str):
        merged["reminders"] = [{"label": label} for label in reminders]

    if "frequency" in merged:
        # Blank or null means unstated; normalize_frequency reads either as
        # Once Daily, which would then demand exactly one reminder slot.
        stated = str(merged["frequency"] or "").strip()
        merged["frequency"] = normalize_frequency(stated) if stated else ""

    if merged.get("medicationType") is not None:
        canonical = normalize_medication_type(merged["medicationType"])
        if canonical:
            merged["medicationType"] = canonical

    if "doctorName" not in merged:
        doc_alias = (
            merged.get("doctor") or merged.get("prescriberName") or merged.get("doctor_name")
        )
        if doc_alias:
            merged["doctorName"] = doc_alias

    if "facilityName" not in merged:
        fac_alias = (
            merged.get("clinicName")
            or merged.get("hospitalName")
            or merged.get("clinic")
            or merged.get("facility_name")
            or merged.get("facility")
        )
        if fac_alias:
            merged["facilityName"] = fac_alias

    if "prescriptionDate" not in merged:
        pdate_alias = merged.get("prescription_date") or merged.get("date")
        if pdate_alias:
            merged["prescriptionDate"] = pdate_alias

    return merged


class MedicationInput(BaseModel):
    name: str
    howMuchToTake: str = ""
    strength: str = ""
    medicationType: Optional[MedicationType] = None
    dosage: Optional[str] = None
    # Blank means the caller stated no frequency, so no reminder count is
    # required. Defaulting to Once Daily would reject any other slot count.
    frequency: Union[MedicationFrequency, str, None] = ""
    instructions: str = ""
    isReminderEnabled: bool = True
    status: str = "Active"
    notes: str = ""
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    prescriptionId: Optional[int] = None
    doctorName: Optional[str] = None
    facilityName: Optional[str] = None
    prescriptionDate: Optional[str] = None
    dailyTargetCount: Optional[int] = Field(default=None, ge=1, le=1000)
    asNeeded: bool = False
    reminderLabels: List[ReminderLabel] = Field(default_factory=list)
    reminders: List[ReminderInput] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def parse_reminder_labels(cls, data):
        return _merge_reminder_fields(data)

    @model_validator(mode="after")
    def normalize_medicine_details(self):
        # Assigning below marks a field as set, which would make exclude_unset
        # report fields the client never sent and blank them on a partial PUT.
        provided = set(self.__pydantic_fields_set__)
        normalized = normalize_medication_payload(self.model_dump())
        self.howMuchToTake = normalized["howMuchToTake"]
        self.strength = normalized["strength"]
        self.dosage = normalized["dosage"]
        self.doctorName = normalized.get("doctorName")
        self.facilityName = normalized.get("facilityName")
        self.prescriptionDate = normalized.get("prescriptionDate")
        stated = (
            self.frequency.value
            if isinstance(self.frequency, MedicationFrequency)
            else str(self.frequency or "")
        ).strip()
        self.frequency = normalize_frequency(stated) if stated else ""
        med_type = normalized.get("medicationType") or self.medicationType
        canonical_type = normalize_medication_type(med_type)
        if canonical_type:
            try:
                self.medicationType = MedicationType(canonical_type)
            except ValueError:
                self.medicationType = MedicationType.OTHER
        self.__pydantic_fields_set__.intersection_update(provided)
        return self


class BulkMedicationInput(BaseModel):
    medications: List[MedicationInput]
    # Off so clearing reminders is honoured instead of refilled.
    autoSchedule: bool = False


PatientDoseStatus = Literal["taken", "skipped", "pending"]


class DoseProgressEntry(BaseModel):
    medicationId: int
    reminderId: Optional[int] = None
    scheduledTime: int
    takenTime: Optional[int] = None
    status: PatientDoseStatus
    delayMinutes: int = 0
    synced: bool = True

    @field_validator("status", mode="before")
    @classmethod
    def reject_missed_status(cls, value: Any) -> Any:
        if str(value).strip().lower() == "missed":
            raise ValueError(
                "status 'missed' is calculated automatically; use 'taken' or "
                "'skipped' before the current configured dose slot ends"
            )
        return value


class DoseProgressUpdate(BaseModel):
    entries: List[DoseProgressEntry]


class SyncDoseLogInput(BaseModel):
    entries: List[DoseProgressEntry] = Field(default_factory=list)


class DailyCountTargetInput(BaseModel):
    """Daily prescribed-use target for count-based medication."""

    dailyTargetCount: int = Field(ge=1, le=1000)


class DailyCountTakenInput(BaseModel):
    """One atomic count-based medication use update."""

    count: int = Field(default=1, ge=1, le=1000)
    takenTime: Optional[int] = Field(default=None, ge=0)


class DailyCountUndoInput(BaseModel):
    """Undo one or more count-based medication uses."""

    count: int = Field(default=1, ge=1, le=1000)


class ScheduleMedicationInput(BaseModel):
    reminderLabels: List[ReminderLabel] = Field(default_factory=list)
    reminders: Optional[List[ReminderInput]] = None
    useFrequencyDefaults: bool = True

    @model_validator(mode="before")
    @classmethod
    def parse_reminder_labels(cls, data):
        return _merge_reminder_fields(data)


class PrescriptionScanInput(BaseModel):
    imageUrl: Optional[str] = None
    sourceUrl: Optional[str] = None
    scannedAt: Optional[int] = None
    prescriptionDate: Optional[str] = None
    prescriberName: Optional[str] = None
    extract: bool = True
    persistMedications: bool = False
    autoSchedule: bool = False


class DeviceTokenInput(BaseModel):
    deviceToken: str
    platform: str = "unknown"
    timezone: Optional[str] = Field(
        default=None,
        description="Device IANA timezone (e.g. UTC, America/New_York). Saved on patient profile when provided.",
    )


class ReminderNotifyInput(BaseModel):
    medicationId: int
    reminderId: Optional[int] = None
    scheduledTime: int
    title: Optional[str] = None
    body: Optional[str] = None
