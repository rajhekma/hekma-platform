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


def extract_patient(row):
    raw = row["data"]
    return {
        "gender": raw.get("gender"),
        "birth_date": raw.get("birthDate"),
    }


def extract_conditions(rows):
    result = {}
    for r in rows:
        raw = r["data"]

        name = safe_get_display(
            raw,
            ["code", "coding", 0, "display"],
            ["code", "text"]
        )

        if name:
            result[name] = {"name": name}

    return list(result.values())


def extract_medications(rows):
    result = {}

    for r in rows:
        raw = r["data"]

        name = safe_get_display(
            raw,
            ["medicationCodeableConcept", "coding", 0, "display"],
            ["medicationCodeableConcept", "text"],
            ["medicationCodeableConcept", "coding", 0, "code"]
        )

        date = (
            raw.get("authoredOn")
            or raw.get("effectiveDateTime")
            or safe_get_display(raw, ["effectivePeriod", "start"])
        )

        if name:
            result[name] = {"name": name, "date": date}

    return list(result.values())


def extract_procedures(rows):
    procedures = []

    for r in rows:
        raw = r["data"]

        name = safe_get_display(
            raw,
            ["code", "coding", 0, "display"]
        )

        date = (
            raw.get("performedDateTime")
            or safe_get_display(raw, ["performedPeriod", "start"])
        )

        if name:
            procedures.append({"name": name, "date": date})

    return procedures


def extract_observations(rows):
    observations = []

    for r in rows:
        raw = r["data"]

        obs_type = safe_get_display(raw, ["code", "coding", 0, "display"])

        value = None
        if raw.get("valueQuantity"):
            v = raw["valueQuantity"]
            value = f"{v.get('value')} {v.get('unit')}"
        elif raw.get("valueString"):
            value = raw.get("valueString")
        elif raw.get("valueDateTime"):
            value = raw.get("valueDateTime")

        if not obs_type or not value:
            continue

        observations.append({
            "type": obs_type,
            "value": value,
            "date": raw.get("effectiveDateTime") or raw.get("issued"),
        })

    return observations


def extract_encounters(rows):
    encounters = []

    for r in rows:
        raw = r["data"]

        encounters.append({
            "type": safe_get_display(raw, ["class", "display"]),
            "start": safe_get_display(raw, ["period", "start"]),
            "end": safe_get_display(raw, ["period", "end"]),
        })

    return encounters


def build_mimic_structured_json(
    patient_row,
    condition_rows,
    medication_rows,
    procedure_rows,
    observation_rows,
    encounter_rows
):
    return {
        "patient": extract_patient(patient_row),
        "encounters": extract_encounters(encounter_rows),
        "conditions": extract_conditions(condition_rows),
        "medications": extract_medications(medication_rows),
        "procedures": extract_procedures(procedure_rows),
        "observations": extract_observations(observation_rows),
    }