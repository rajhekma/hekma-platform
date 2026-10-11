from typing import List, Literal, Optional

from pydantic import BaseModel, Field


CompliancePeriod = Literal["7d", "1m", "6m", "1y"]


class LastDoseTaken(BaseModel):
    takenTime: Optional[int] = None
    label: Optional[str] = None


class ComplianceSummary(BaseModel):
    # null when no dose was due in the period — adherence is undefined, not 100%.
    overallCompliancePercentage: Optional[float] = None
    complianceChangeVsPreviousPeriod: float
    totalActivePatients: int
    missedDosesToday: int
    totalMissedDosesThisWeek: int
    totalMissedDosesInPeriod: int
    activeDosage: int
    activeMedicationsCount: int
    # Every medication on record, including inactive ones.
    totalMedicationsCount: int = 0
    brandNameMedicationsCount: int = 0


class ComplianceTrendPoint(BaseModel):
    date: str
    compliancePercentage: Optional[float] = None
    takenCount: int = 0
    missedCount: int = 0
    skippedCount: int = 0
    pendingCount: int = 0
    dueCount: int = 0


class PatientComplianceRow(BaseModel):
    patientId: str
    patientName: str
    medicationId: int
    medicationDisplay: str
    compliancePercentage: Optional[float] = None
    missedDoses: int
    dosesDue: int = 0
    dosesTaken: int = 0
    dosesSkipped: int = 0
    dosesPending: int = 0
    activeDosage: int = 0
    lastDoseTaken: LastDoseTaken


class PatientCompliancePage(BaseModel):
    total: int
    page: int
    limit: int
    entries: List[PatientComplianceRow]


class ComplianceDashboardResponse(BaseModel):
    period: str
    summary: ComplianceSummary
    complianceTrend: List[ComplianceTrendPoint]
    missedDosesByShift: dict
    patients: PatientCompliancePage
