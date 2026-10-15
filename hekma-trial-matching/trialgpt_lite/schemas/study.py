"""
Pydantic data models for ClinicalTrials.gov study protocols and eligibility.
"""

from typing import Optional
from pydantic import BaseModel, Field


class DemographicCriteria(BaseModel):
    """Demographic restrictions defined by study protocol."""
    minimum_age_years: Optional[float] = Field(default=None, description="Minimum age in years, or None if no lower limit.")
    maximum_age_years: Optional[float] = Field(default=None, description="Maximum age in years, or None if no upper limit.")
    minimum_age_text: Optional[str] = Field(default=None, description="Raw minimum age string e.g. '18 Years'.")
    maximum_age_text: Optional[str] = Field(default=None, description="Raw maximum age string e.g. '75 Years'.")
    sex: str = Field(default="ALL", description="Gender restrictions: ALL, FEMALE, or MALE.")
    healthy_volunteers: Optional[bool] = Field(default=None, description="Whether healthy volunteers are accepted.")


class ParsedCriteria(BaseModel):
    """Parsed inclusion and exclusion criteria blocks."""
    inclusion_criteria: list[str] = Field(default_factory=list, description="List of discrete inclusion criteria.")
    exclusion_criteria: list[str] = Field(default_factory=list, description="List of discrete exclusion criteria.")
    raw_text: str = Field(default="", description="Original unparsed eligibility text.")


class StudyContact(BaseModel):
    """Central contact person for study recruitment."""
    name: Optional[str] = Field(default=None, description="Full name or title of contact.")
    role: Optional[str] = Field(default=None, description="Role, e.g. Study Contact.")
    phone: Optional[str] = Field(default=None, description="Phone number.")
    email: Optional[str] = Field(default=None, description="Email address.")


class StudyOfficial(BaseModel):
    """Overall study official / Principal Investigator."""
    name: Optional[str] = Field(default=None, description="Investigator full name.")
    affiliation: Optional[str] = Field(default=None, description="Institutional affiliation.")
    role: Optional[str] = Field(default=None, description="Role, e.g. PRINCIPAL_INVESTIGATOR, STUDY_DIRECTOR.")


class StudyLocation(BaseModel):
    """Facility or site location where trial is conducted."""
    facility: Optional[str] = Field(default=None, description="Hospital, clinic or facility name.")
    city: Optional[str] = Field(default=None, description="City name.")
    state: Optional[str] = Field(default=None, description="State or province.")
    country: Optional[str] = Field(default=None, description="Country name.")


class ContactsAndLocations(BaseModel):
    """Collection of study contacts, investigators, and site locations."""
    central_contacts: list[StudyContact] = Field(default_factory=list)
    overall_officials: list[StudyOfficial] = Field(default_factory=list)
    locations: list[StudyLocation] = Field(default_factory=list)


class InterventionItem(BaseModel):
    """Structured detail of a single trial intervention (drug, procedure, device)."""
    type: Optional[str] = Field(default=None, description="Intervention type, e.g. DRUG, BIOLOGICAL, DEVICE.")
    name: str = Field(..., description="Name of intervention or drug.")
    description: Optional[str] = Field(default=None, description="Detailed regimen or dosing description.")


class StudyDesign(BaseModel):
    """Scientific trial architecture and design parameters."""
    allocation: Optional[str] = Field(default=None, description="e.g. RANDOMIZED, NON_RANDOMIZED.")
    intervention_model: Optional[str] = Field(default=None, description="e.g. PARALLEL, SINGLE_GROUP, CROSSOVER.")
    primary_purpose: Optional[str] = Field(default=None, description="e.g. TREATMENT, PREVENTION, DIAGNOSTIC.")
    masking: Optional[str] = Field(default=None, description="e.g. DOUBLE, QUADRUPLE, NONE (OPEN LABEL).")


class StudyEnrollment(BaseModel):
    """Enrollment volume and count specifications."""
    count: Optional[int] = Field(default=None, description="Planned or actual participant count.")
    type: Optional[str] = Field(default=None, description="ESTIMATED or ACTUAL.")


class StudyTimeline(BaseModel):
    """Key milestone dates for the protocol."""
    start_date: Optional[str] = Field(default=None, description="Study start date.")
    start_date_type: Optional[str] = Field(default=None, description="ACTUAL or ESTIMATED.")
    primary_completion_date: Optional[str] = Field(default=None, description="Primary outcome completion date.")
    completion_date: Optional[str] = Field(default=None, description="Study completion date.")
    first_posted: Optional[str] = Field(default=None, description="Date first posted on ClinicalTrials.gov.")
    last_updated: Optional[str] = Field(default=None, description="Last update date posted on ClinicalTrials.gov.")


class StudyOutcome(BaseModel):
    """Specified primary or secondary clinical outcome measure."""
    measure: str = Field(..., description="Name of specific outcome measure.")
    time_frame: Optional[str] = Field(default=None, description="Time frame for assessment.")
    description: Optional[str] = Field(default=None, description="Measurement details and criteria.")


class TrialStudy(BaseModel):
    """Normalized clinical trial protocol representation."""
    nct_id: str = Field(..., description="Unique NCT Identifier, e.g., NCT05801029.")
    brief_title: str = Field(..., description="Brief title of the study.")
    official_title: Optional[str] = Field(default=None, description="Official title if available.")
    overall_status: str = Field(default="UNKNOWN", description="Recruitment/study status (e.g. RECRUITING).")
    study_type: Optional[str] = Field(default="INTERVENTIONAL", description="e.g. INTERVENTIONAL, OBSERVATIONAL.")
    conditions: list[str] = Field(default_factory=list, description="Medical conditions addressed by the study.")
    interventions: list[str] = Field(default_factory=list, description="List of drugs, biologics, or interventions.")
    detailed_interventions: list[InterventionItem] = Field(default_factory=list, description="Structured intervention details.")
    phases: list[str] = Field(default_factory=list, description="Study phase (e.g., PHASE1, PHASE2, PHASE3).")
    brief_summary: Optional[str] = Field(default=None, description="Short summary of the trial protocol.")
    lead_sponsor: Optional[str] = Field(default=None, description="Lead sponsor organization.")
    collaborators: list[str] = Field(default_factory=list, description="Collaborating organizations.")
    design: Optional[StudyDesign] = Field(default=None, description="Design, allocation, and masking.")
    enrollment: Optional[StudyEnrollment] = Field(default=None, description="Target enrollment metrics.")
    timeline: Optional[StudyTimeline] = Field(default=None, description="Key study milestone dates.")
    primary_outcomes: list[StudyOutcome] = Field(default_factory=list, description="Primary clinical outcomes.")
    secondary_outcomes: list[StudyOutcome] = Field(default_factory=list, description="Secondary clinical outcomes.")
    demographics: DemographicCriteria = Field(default_factory=DemographicCriteria)
    criteria: ParsedCriteria = Field(default_factory=ParsedCriteria)
    contacts: ContactsAndLocations = Field(default_factory=ContactsAndLocations)
    web_url: str = Field(default="", description="Web URL to clinicaltrials.gov record.")

    def model_post_init(self, __context):
        if not self.web_url and self.nct_id:
            self.web_url = f"https://clinicaltrials.gov/study/{self.nct_id}"
