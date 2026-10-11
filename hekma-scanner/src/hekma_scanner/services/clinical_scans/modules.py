from enum import Enum


class ClinicalModule(str, Enum):
    """Supported OCR scan modules and their MySQL target tables."""

    ALLERGIES = "allergies"
    LAB_REPORTS = "lab_reports"
    VITAL_SIGNS = "vital_signs"
    IMMUNIZATION = "immunization"
    PROCEDURES = "procedures"
    DIAGNOSIS = "diagnosis"
    MEDICATIONS = "medications"

    @property
    def target_table(self) -> str:
        return {
            ClinicalModule.ALLERGIES: "Allergies",
            ClinicalModule.LAB_REPORTS: "LabReports",
            ClinicalModule.VITAL_SIGNS: "Vitalsign",
            ClinicalModule.IMMUNIZATION: "Immunization",
            ClinicalModule.PROCEDURES: "Procedures",
            ClinicalModule.DIAGNOSIS: "MedicalCondition",
            ClinicalModule.MEDICATIONS: "medications",
        }[self]

    @classmethod
    def from_value(cls, value: str) -> "ClinicalModule":
        normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "allergy": cls.ALLERGIES,
            "allergies": cls.ALLERGIES,
            "lab": cls.LAB_REPORTS,
            "labs": cls.LAB_REPORTS,
            "lab_report": cls.LAB_REPORTS,
            "lab_reports": cls.LAB_REPORTS,
            "vital": cls.VITAL_SIGNS,
            "vitals": cls.VITAL_SIGNS,
            "vital_sign": cls.VITAL_SIGNS,
            "vital_signs": cls.VITAL_SIGNS,
            "immunization": cls.IMMUNIZATION,
            "immunizations": cls.IMMUNIZATION,
            "vaccine": cls.IMMUNIZATION,
            "procedure": cls.PROCEDURES,
            "procedures": cls.PROCEDURES,
            "diagnosis": cls.DIAGNOSIS,
            "diagnoses": cls.DIAGNOSIS,
            "condition": cls.DIAGNOSIS,
            "medical_condition": cls.DIAGNOSIS,
            "medication": cls.MEDICATIONS,
            "medications": cls.MEDICATIONS,
            "medicine": cls.MEDICATIONS,
            "medicines": cls.MEDICATIONS,
            "prescription": cls.MEDICATIONS,
            "prescriptions": cls.MEDICATIONS,
            "rx": cls.MEDICATIONS,
        }
        if normalized not in aliases:
            raise ValueError(f"Unsupported clinical module: {value}")
        return aliases[normalized]

    @property
    def dashboard_object_type(self) -> str:
        """FHIR eventType used by GET /patientdetail Redis keys."""
        return {
            ClinicalModule.ALLERGIES: "AllergyIntolerance",
            ClinicalModule.LAB_REPORTS: "Observation",
            ClinicalModule.VITAL_SIGNS: "Observation",
            ClinicalModule.IMMUNIZATION: "Immunization",
            ClinicalModule.PROCEDURES: "Procedure",
            ClinicalModule.DIAGNOSIS: "Condition",
            ClinicalModule.MEDICATIONS: "MedicationRequest",
        }[self]
