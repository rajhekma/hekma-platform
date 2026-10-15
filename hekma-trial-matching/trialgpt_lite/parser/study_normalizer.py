"""
Normalizer for transforming ClinicalTrials.gov API study objects into TrialStudy Pydantic instances.
Extracts comprehensive study protocol modules: identification, design, enrollment,
sponsors, interventions, timeline dates, outcomes, eligibility, and site locations.
"""

from typing import Any
from trialgpt_lite.schemas.study import (
    TrialStudy,
    StudyContact,
    StudyOfficial,
    StudyLocation,
    ContactsAndLocations,
    InterventionItem,
    StudyDesign,
    StudyEnrollment,
    StudyTimeline,
    StudyOutcome,
)
from trialgpt_lite.parser.criteria_parser import parse_eligibility_criteria, parse_demographics


def normalize_study(raw_study: dict[str, Any]) -> TrialStudy:
    """
    Normalizes a single study payload from ClinicalTrials.gov v2 API into TrialStudy.
    """
    protocol = raw_study.get("protocolSection", {})

    # 1. Identification Module
    ident = protocol.get("identificationModule", {})
    nct_id = ident.get("nctId", "UNKNOWN")
    brief_title = ident.get("briefTitle", "Untitled Study")
    official_title = ident.get("officialTitle")

    # 2. Status & Timeline Module
    status_mod = protocol.get("statusModule", {})
    overall_status = status_mod.get("overallStatus", "UNKNOWN")
    timeline = StudyTimeline(
        start_date=status_mod.get("startDateStruct", {}).get("date"),
        start_date_type=status_mod.get("startDateStruct", {}).get("type"),
        primary_completion_date=status_mod.get("primaryCompletionDateStruct", {}).get("date"),
        completion_date=status_mod.get("completionDateStruct", {}).get("date"),
        first_posted=status_mod.get("studyFirstPostDateStruct", {}).get("date"),
        last_updated=status_mod.get("lastUpdatePostDateStruct", {}).get("date"),
    )

    # 3. Conditions Module
    cond_mod = protocol.get("conditionsModule", {})
    conditions = cond_mod.get("conditions", [])

    # 4. Design & Phase Module
    design_mod = protocol.get("designModule", {})
    study_type = design_mod.get("studyType", "INTERVENTIONAL")
    phases = design_mod.get("phases", [])
    
    design_info = design_mod.get("designInfo", {})
    design = StudyDesign(
        allocation=design_info.get("allocation"),
        intervention_model=design_info.get("interventionModel"),
        primary_purpose=design_info.get("primaryPurpose"),
        masking=design_info.get("maskingInfo", {}).get("masking"),
    )

    enrollment_info = design_mod.get("enrollmentInfo", {})
    enrollment = StudyEnrollment(
        count=enrollment_info.get("count"),
        type=enrollment_info.get("type"),
    )

    # 5. Description Module
    desc_mod = protocol.get("descriptionModule", {})
    brief_summary = desc_mod.get("briefSummary")

    # 6. Interventions Module
    arms_mod = protocol.get("armsInterventionsModule", {})
    interventions_raw = arms_mod.get("interventions", [])
    interventions = [
        f"{item.get('type', '')}: {item.get('name', '')}".strip(": ")
        for item in interventions_raw
        if item.get("name")
    ]
    detailed_interventions = [
        InterventionItem(
            type=item.get("type"),
            name=item.get("name", "Unnamed Intervention"),
            description=item.get("description"),
        )
        for item in interventions_raw
        if item.get("name")
    ]

    # 7. Sponsor & Collaborators Module
    sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})
    lead_sponsor = sponsor_mod.get("leadSponsor", {}).get("name")
    collaborators = [c.get("name") for c in sponsor_mod.get("collaborators", []) if c.get("name")]

    # 8. Outcomes Module
    outcomes_mod = protocol.get("outcomesModule", {})
    primary_outcomes = [
        StudyOutcome(
            measure=o.get("measure", ""),
            time_frame=o.get("timeFrame"),
            description=o.get("description"),
        )
        for o in outcomes_mod.get("primaryOutcomes", [])
        if o.get("measure")
    ]
    secondary_outcomes = [
        StudyOutcome(
            measure=o.get("measure", ""),
            time_frame=o.get("timeFrame"),
            description=o.get("description"),
        )
        for o in outcomes_mod.get("secondaryOutcomes", [])
        if o.get("measure")
    ]

    # 9. Eligibility Module
    elig_mod = protocol.get("eligibilityModule", {})
    criteria_text = elig_mod.get("eligibilityCriteria", "")
    demographics = parse_demographics(elig_mod)
    criteria = parse_eligibility_criteria(criteria_text)

    # 10. Contacts & Locations Module
    contacts_mod = protocol.get("contactsLocationsModule", {})

    central_contacts = []
    for c in contacts_mod.get("centralContacts", []):
        if c.get("name") or c.get("email") or c.get("phone"):
            central_contacts.append(StudyContact(
                name=c.get("name"),
                role=c.get("role"),
                phone=c.get("phone"),
                email=c.get("email"),
            ))

    overall_officials = []
    for o in contacts_mod.get("overallOfficials", []):
        if o.get("name"):
            overall_officials.append(StudyOfficial(
                name=o.get("name"),
                affiliation=o.get("affiliation"),
                role=o.get("role"),
            ))

    locations = []
    for loc in contacts_mod.get("locations", []):
        if loc.get("facility") or loc.get("city") or loc.get("country"):
            locations.append(StudyLocation(
                facility=loc.get("facility"),
                city=loc.get("city"),
                state=loc.get("state"),
                country=loc.get("country"),
            ))

    contacts = ContactsAndLocations(
        central_contacts=central_contacts,
        overall_officials=overall_officials,
        locations=locations,
    )

    return TrialStudy(
        nct_id=nct_id,
        brief_title=brief_title,
        official_title=official_title,
        overall_status=overall_status,
        study_type=study_type,
        conditions=conditions,
        interventions=interventions,
        detailed_interventions=detailed_interventions,
        phases=phases,
        brief_summary=brief_summary,
        lead_sponsor=lead_sponsor,
        collaborators=collaborators,
        design=design,
        enrollment=enrollment,
        timeline=timeline,
        primary_outcomes=primary_outcomes,
        secondary_outcomes=secondary_outcomes,
        demographics=demographics,
        criteria=criteria,
        contacts=contacts,
    )
