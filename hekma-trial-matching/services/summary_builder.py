
def safe_get_display(resource, *paths):
    for path in paths:
        value = resource
        try:
            for key in path:
                value = value[key]
            if value:
                return value
        except Exception:
            continue
    return None


def extract_conditions(rows):
    conditions = []
    for row in rows:
        raw = row["raw_resource"]
        conditions.append({
            "name": safe_get_display(
                raw,
                ["code", "text"],
                ["code", "coding", 0, "display"],
            ),
            "clinical_status": raw.get("clinicalStatus"),
            "verification_status": raw.get("verificationStatus"),
            "onset_date": raw.get("onsetDateTime") or raw.get("recordedDate"),
        })
    return conditions


def extract_medications(rows):
    meds = []
    for row in rows:
        raw = row["raw_resource"]
        meds.append({
            "name": safe_get_display(
                raw,
                ["medicationCodeableConcept", "text"],
                ["medicationCodeableConcept", "coding", 0, "display"],
            ),
            "status": raw.get("status"),
            "date_written": raw.get("dateWritten") or raw.get("authoredOn"),
        })
    return meds


def extract_immunizations(rows):
    vaccines = []
    for row in rows:
        raw = row["raw_resource"]
        vaccines.append({
            "vaccine": safe_get_display(
                raw,
                ["vaccineCode", "text"],
                ["vaccineCode", "coding", 0, "display"],
            ),
            "status": raw.get("status"),
            "date": raw.get("occurrenceDateTime"),
        })
    return vaccines


def build_structured_json(
    patient_row,
    condition_rows,
    allergy_rows,
    medication_rows,
    immunization_rows,
    procedure_rows,
    observation_rows,
):
    demographics = {
        #"given_name": patient_row.get("given_name"),
        #"family_name": patient_row.get("family_name"),
        "gender": patient_row["raw_resource"].get("gender"),
        "birth_date": patient_row["raw_resource"].get("birthDate"),
    }

    return {
        "demographics": demographics,
        "conditions": extract_conditions(condition_rows),
        "allergies": extract_allergies(allergy_rows),
        "medications": extract_medications(medication_rows),
        "immunizations": extract_immunizations(immunization_rows),
        "procedures": extract_procedures(procedure_rows),
        "observations": extract_observations(observation_rows),
    }
    


def extract_allergies(rows):
    allergies = []
    for row in rows:
        raw = row["raw_resource"]
        allergies.append({
            "name": safe_get_display(
                raw,
                ["code", "text"],
                ["code", "coding", 0, "display"],
            ),
            "status": raw.get("status"),
            "criticality": raw.get("criticality"),
            "onset_date": raw.get("onsetDateTime"),
        })
    return allergies


def extract_procedures(rows):
    procedures = []
    for row in rows:
        raw = row["raw_resource"]
        procedures.append({
            "name": safe_get_display(
                raw,
                ["code", "text"],
                ["code", "coding", 0, "display"],
            ),
            "status": raw.get("status"),
            "date": (
                raw.get("performedPeriod", {}).get("start")
                or raw.get("performedDateTime")
            ),
        })
    return procedures


def extract_observations(rows):
    observations = []
    for row in rows:
        raw = row["raw_resource"]

        value_quantity = raw.get("valueQuantity", {})
        value = None
        if value_quantity:
            value = f"{value_quantity.get('value')} {value_quantity.get('unit')}"

        observations.append({
            "type": safe_get_display(
                raw,
                ["code", "text"],
                ["code", "coding", 0, "display"],
            ),
            "value": value,
            "date": raw.get("effectiveDateTime") or raw.get("issued"),
        })
    return observations
