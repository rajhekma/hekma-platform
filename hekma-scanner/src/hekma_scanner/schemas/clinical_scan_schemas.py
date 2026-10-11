from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from ..utils.vital_signs_normalization import normalize_vital_sign_record



# ── New: Smart universal scan input ─────────────────────────────────────────

class SmartClinicalScanUrlInput(BaseModel):
    """Input for POST /clinical-scans/smart/url — auto-detects all modules."""
    sourceUrl:      Optional[str]        = None
    imageUrl:       Optional[str]        = None
    persistRecords: bool                 = False
    forceSave:      bool                 = Field(
        False,
        description="Bypass duplicate blocking and upsert existing scan/records.",
    )
    modules:        Optional[List[str]]  = Field(
        None,
        description="Optional list of modules to save (e.g. ['lab_reports', 'vital_signs', 'medications']). "
                    "If omitted, all detected modules are saved."
    )
    autoSchedule:   bool                 = Field(
        False,
        description="Fall back to frequency-default reminder slots when the document "
                    "does not say when to take a dose. Off by default so no slot is invented.",
    )
    documentDate:   Optional[str]        = None
    providerName:   Optional[str]        = None


# ── New: CRUD input schemas for all 6 clinical record modules ────────────────

class AllergyInput(BaseModel):
    substance:   str
    criticality: Optional[str] = Field(None, description="high | low")
    category:    Optional[str] = Field(None, description="medication | food | environment")
    status:      Optional[str] = Field(None, description="active | inactive")
    reaction:    Optional[str] = None
    onsetDate:   Optional[str] = None
    notes:       Optional[str] = None


class LabReportInput(BaseModel):
    testName:       Optional[str] = None
    fieldKey:       Optional[str] = None
    loincCode:      Optional[str] = None
    testValue:      Optional[str] = None
    unit:           Optional[str] = None
    referenceRange: Optional[str] = None
    resultDate:     Optional[str] = None
    notes:          Optional[str] = None

    @model_validator(mode="after")
    def require_standard_key_or_name(self):
        if not self.fieldKey and not self.testName:
            raise ValueError("fieldKey or testName is required")
        return self


class VitalSignInput(BaseModel):
    type:              Optional[str] = None
    fieldKey:          Optional[str] = None
    loincCode:         Optional[str] = None
    refValue1:         str
    refValue2:         Optional[str] = None
    metric:            Optional[str] = None
    dateOfObservation: Optional[str] = None
    notes:             Optional[str] = None

    @model_validator(mode="after")
    def require_standard_key_or_type(self):
        if not self.fieldKey and not self.type:
            raise ValueError("fieldKey or type is required")
        return self

    @model_validator(mode="after")
    def normalize_bp_values(self):
        normalized = normalize_vital_sign_record(self.model_dump())
        for key, value in normalized.items():
            if key in self.model_fields:
                setattr(self, key, value)
        return self


class ImmunizationInput(BaseModel):
    vaccineName:     str
    vaccinationDate: Optional[str] = None
    notes:           Optional[str] = None


class ProcedureInput(BaseModel):
    procedureName: str
    status:        Optional[str] = None
    startDate:     Optional[str] = None
    endDate:       Optional[str] = None
    reason:        Optional[str] = None
    notes:         Optional[str] = None


class DiagnosisInput(BaseModel):
    conditionName: str
    status:        Optional[str] = None
    startDate:     Optional[str] = None
    endDate:       Optional[str] = None
    notes:         Optional[str] = None
