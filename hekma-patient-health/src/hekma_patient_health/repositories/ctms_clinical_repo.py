"""MySQL CTMS write repos for clinical OCR persistence."""

from datetime import date, datetime, timezone
from typing import Optional

from ..awsutils.mysql_db_connection import mysql_connection
from ..services.clinical_fhir.mappers import allergy_fhir_criticality, normalize_allergy_severity


from ..services.clinical_scans.exceptions import RecordAlreadyExistsError


class DuplicateClinicalRecordError(RecordAlreadyExistsError):
    def __init__(self, message: str, existing_record_id: str = ""):
        super().__init__(message, existing_record_id=existing_record_id)


def _date_only(value: Optional[str]) -> Optional[str]:
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return value[:10] if len(value) >= 10 else value


def _enrich_notes(notes: Optional[str], extra_fields: dict) -> str:
    """Intelligently appends FHIR-rich clinical metadata (body site, code, performer, outcome, interpretation) into notes."""
    base_notes = (notes or "").strip()
    extra_lines = []
    for label, val in extra_fields.items():
        if val and str(val).strip():
            val_str = str(val).strip()
            if val_str.lower() not in base_notes.lower():
                extra_lines.append(f"{label}: {val_str}")
    if extra_lines:
        added = "\n".join(extra_lines)
        return f"{base_notes}\n{added}".strip() if base_notes else added
    return base_notes


def find_lab_report(patient_id: str, test_name: str, result_date: Optional[str] = None):
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        if result_date:
            cur.execute(
                """
                SELECT * FROM LabReports
                WHERE patientId = %s
                  AND LOWER(TRIM(testName)) = LOWER(TRIM(%s))
                  AND DATE(resultDate) = DATE(%s)
                  AND (is_deleted IS NULL OR is_deleted = 0)
                LIMIT 1
                """,
                (patient_id, test_name, _date_only(result_date)),
            )
        else:
            cur.execute(
                """
                SELECT * FROM LabReports
                WHERE patientId = %s
                  AND LOWER(TRIM(testName)) = LOWER(TRIM(%s))
                  AND (is_deleted IS NULL OR is_deleted = 0)
                LIMIT 1
                """,
                (patient_id, test_name),
            )
        return cur.fetchone()


def create_lab_report(patient_id: str, data: dict) -> dict:
    test_name = (data.get("testName") or "").strip()
    result_date = _date_only(data.get("resultDate") or data.get("date"))
    existing = find_lab_report(patient_id, test_name, result_date)
    if existing:
        raise DuplicateClinicalRecordError(
            f"Lab report '{test_name}' already exists for patient {patient_id}",
            existing_record_id=str(existing["id"]),
        )
    extra_notes = {
        "Field Key": data.get("fieldKey"),
        "Test Code": data.get("loincCode") or data.get("testCode"),
        "Category": data.get("category"),
        "Interpretation": data.get("interpretation"),
        "Specimen": data.get("specimen"),
        "Performer": data.get("performer"),
    }
    notes = _enrich_notes(data.get("notes"), extra_notes)
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO LabReports (
                patientId, testName, resultDate, notes, imageUrl,
                testValue, unit, referenceRange, is_deleted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
            """,
            (
                patient_id,
                test_name,
                result_date,
                notes,
                data.get("imageUrl"),
                data.get("testValue") or data.get("value"),
                data.get("unit"),
                data.get("referenceRange"),
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM LabReports WHERE id = %s", (cur.lastrowid,))
        return dict(cur.fetchone())


def find_vital(patient_id: str, vital_type: str, observed_at: Optional[str] = None):
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        if observed_at:
            cur.execute(
                """
                SELECT * FROM Vitalsign
                WHERE patientId = %s
                  AND LOWER(TRIM(type)) = LOWER(TRIM(%s))
                  AND DATE(dateOfObservation) = DATE(%s)
                  AND (is_deleted IS NULL OR is_deleted = 0)
                LIMIT 1
                """,
                (patient_id, vital_type, _date_only(observed_at)),
            )
        else:
            cur.execute(
                """
                SELECT * FROM Vitalsign
                WHERE patientId = %s
                  AND LOWER(TRIM(type)) = LOWER(TRIM(%s))
                  AND (is_deleted IS NULL OR is_deleted = 0)
                LIMIT 1
                """,
                (patient_id, vital_type),
            )
        return cur.fetchone()


def create_vital(patient_id: str, data: dict) -> dict:
    vital_type = (data.get("type") or data.get("name") or "").strip()
    observed_at = _date_only(data.get("dateOfObservation") or data.get("date"))
    existing = find_vital(patient_id, vital_type, observed_at)
    if existing:
        raise DuplicateClinicalRecordError(
            f"Vital '{vital_type}' already exists for patient {patient_id}",
            existing_record_id=str(existing["id"]),
        )
    extra_notes = {
        "Field Key": data.get("fieldKey"),
        "LOINC Code": data.get("loincCode"),
        "Interpretation": data.get("interpretation"),
        "Body Site": data.get("bodySite"),
        "Position": data.get("patientPosition"),
    }
    notes = _enrich_notes(data.get("notes"), extra_notes)
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO Vitalsign (
                patientId, dateOfObservation, type, refValue1, refValue2,
                metric, tags, notes, is_deleted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
            """,
            (
                patient_id,
                observed_at,
                vital_type,
                data.get("refValue1") or data.get("value"),
                data.get("refValue2"),
                data.get("metric") or data.get("unit"),
                data.get("tags"),
                notes,
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM Vitalsign WHERE id = %s", (cur.lastrowid,))
        return dict(cur.fetchone())


def find_immunization(patient_id: str, vaccine_name: str, vaccination_date: Optional[str] = None):
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        if vaccination_date:
            cur.execute(
                """
                SELECT * FROM Immunization
                WHERE patientId = %s
                  AND LOWER(TRIM(vaccineName)) = LOWER(TRIM(%s))
                  AND DATE(vaccinationDate) = DATE(%s)
                  AND (is_deleted IS NULL OR is_deleted = 0)
                LIMIT 1
                """,
                (patient_id, vaccine_name, _date_only(vaccination_date)),
            )
        else:
            cur.execute(
                """
                SELECT * FROM Immunization
                WHERE patientId = %s
                  AND LOWER(TRIM(vaccineName)) = LOWER(TRIM(%s))
                  AND (is_deleted IS NULL OR is_deleted = 0)
                LIMIT 1
                """,
                (patient_id, vaccine_name),
            )
        return cur.fetchone()


def create_immunization(patient_id: str, data: dict) -> dict:
    vaccine_name = (data.get("vaccineName") or data.get("name") or "").strip()
    vaccination_date = _date_only(data.get("vaccinationDate") or data.get("date"))
    existing = find_immunization(patient_id, vaccine_name, vaccination_date)
    if existing:
        raise DuplicateClinicalRecordError(
            f"Immunization '{vaccine_name}' already exists for patient {patient_id}",
            existing_record_id=str(existing["id"]),
        )
    extra_notes = {
        "Vaccine Code": data.get("vaccineCode"),
        "Dose": data.get("doseQuantity"),
        "Lot Number": data.get("lotNumber"),
        "Manufacturer": data.get("manufacturer"),
        "Expiration Date": data.get("expirationDate"),
        "Site": data.get("site"),
        "Route": data.get("route"),
        "Performer": data.get("performer"),
    }
    notes = _enrich_notes(data.get("notes"), extra_notes)
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO Immunization (
                patientId, vaccineName, vaccinationDate, notes, is_deleted
            )
            VALUES (%s, %s, %s, %s, 0)
            """,
            (
                patient_id,
                vaccine_name,
                vaccination_date,
                notes,
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM Immunization WHERE id = %s", (cur.lastrowid,))
        return dict(cur.fetchone())


def find_procedure(patient_id: str, procedure_name: str, start_date: Optional[str] = None):
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        if start_date:
            cur.execute(
                """
                SELECT * FROM Procedures
                WHERE patientId = %s
                  AND LOWER(TRIM(procedureName)) = LOWER(TRIM(%s))
                  AND DATE(startDate) = DATE(%s)
                  AND (is_deleted IS NULL OR is_deleted != 'Y')
                LIMIT 1
                """,
                (patient_id, procedure_name, _date_only(start_date)),
            )
        else:
            cur.execute(
                """
                SELECT * FROM Procedures
                WHERE patientId = %s
                  AND LOWER(TRIM(procedureName)) = LOWER(TRIM(%s))
                  AND (is_deleted IS NULL OR is_deleted != 'Y')
                LIMIT 1
                """,
                (patient_id, procedure_name),
            )
        return cur.fetchone()


def create_procedure(patient_id: str, data: dict) -> dict:
    procedure_name = (data.get("procedureName") or data.get("name") or "").strip()
    start_date = _date_only(data.get("startDate") or data.get("date"))
    existing = find_procedure(patient_id, procedure_name, start_date)
    if existing:
        raise DuplicateClinicalRecordError(
            f"Procedure '{procedure_name}' already exists for patient {patient_id}",
            existing_record_id=str(existing["id"]),
        )
    extra_notes = {
        "Code": data.get("code"),
        "Category": data.get("category"),
        "Body Site": data.get("bodySite") or data.get("location"),
        "Performer": data.get("performer"),
        "Facility": data.get("facility"),
        "Outcome": data.get("outcome"),
        "Complication": data.get("complication"),
        "Follow Up": data.get("followUp"),
    }
    notes = _enrich_notes(data.get("notes"), extra_notes)
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO Procedures (
                patientId, procedureName, status, startDate, endDate,
                location, reason, notes, is_deleted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'N')
            """,
            (
                patient_id,
                procedure_name,
                (data.get("status") or "completed").upper(),
                start_date,
                _date_only(data.get("endDate")) if data.get("endDate") else None,
                data.get("bodySite") or data.get("location"),
                data.get("reason"),
                notes,
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM Procedures WHERE id = %s", (cur.lastrowid,))
        return dict(cur.fetchone())


def find_condition(patient_id: str, condition_name: str, start_date: Optional[str] = None):
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        if start_date:
            cur.execute(
                """
                SELECT * FROM MedicalCondition
                WHERE patientId = %s
                  AND LOWER(TRIM(conditionName)) = LOWER(TRIM(%s))
                  AND DATE(startDate) = DATE(%s)
                  AND (is_deleted IS NULL OR is_deleted != 'Y')
                LIMIT 1
                """,
                (patient_id, condition_name, _date_only(start_date)),
            )
        else:
            cur.execute(
                """
                SELECT * FROM MedicalCondition
                WHERE patientId = %s
                  AND LOWER(TRIM(conditionName)) = LOWER(TRIM(%s))
                  AND (is_deleted IS NULL OR is_deleted != 'Y')
                LIMIT 1
                """,
                (patient_id, condition_name),
            )
        return cur.fetchone()


def create_condition(patient_id: str, data: dict) -> dict:
    condition_name = (data.get("conditionName") or data.get("name") or "").strip()
    start_date = _date_only(data.get("startDate") or data.get("date"))
    existing = find_condition(patient_id, condition_name, start_date)
    if existing:
        raise DuplicateClinicalRecordError(
            f"Diagnosis '{condition_name}' already exists for patient {patient_id}",
            existing_record_id=str(existing["id"]),
        )
    extra_notes = {
        "Code": data.get("code"),
        "Verification Status": data.get("verificationStatus"),
        "Category": data.get("category"),
        "Severity": data.get("severity"),
        "Body Site": data.get("bodySite"),
        "Recorded By": data.get("recordedBy"),
    }
    notes = _enrich_notes(data.get("notes"), extra_notes)
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO MedicalCondition (
                patientId, conditionName, status, startDate, endDate, notes, is_deleted
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'N')
            """,
            (
                patient_id,
                condition_name,
                (data.get("status") or "active").upper(),
                start_date,
                _date_only(data.get("endDate")) if data.get("endDate") else None,
                notes,
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM MedicalCondition WHERE id = %s", (cur.lastrowid,))
        return dict(cur.fetchone())


# ── Update functions (one per table) ────────────────────────────────────────

def update_lab_report(patient_id: str, record_id: int, data: dict) -> Optional[dict]:
    """Update a LabReport row. Returns updated row or None if not found/owned."""
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE LabReports
            SET testName       = COALESCE(%s, testName),
                testValue      = COALESCE(%s, testValue),
                unit           = COALESCE(%s, unit),
                referenceRange = COALESCE(%s, referenceRange),
                resultDate     = COALESCE(%s, resultDate),
                notes          = COALESCE(%s, notes)
            WHERE id = %s AND patientId = %s AND (is_deleted IS NULL OR is_deleted = 0)
            """,
            (
                data.get("testName"),
                data.get("testValue"),
                data.get("unit"),
                data.get("referenceRange"),
                _date_only(data.get("resultDate")) if data.get("resultDate") else None,
                data.get("notes"),
                record_id,
                patient_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        cur.execute("SELECT * FROM LabReports WHERE id = %s", (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_vital(patient_id: str, record_id: int, data: dict) -> Optional[dict]:
    """Update a Vitalsign row. Returns updated row or None if not found/owned."""
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE Vitalsign
            SET type              = COALESCE(%s, type),
                refValue1         = COALESCE(%s, refValue1),
                refValue2         = COALESCE(%s, refValue2),
                metric            = COALESCE(%s, metric),
                dateOfObservation = COALESCE(%s, dateOfObservation),
                notes             = COALESCE(%s, notes)
            WHERE id = %s AND patientId = %s AND (is_deleted IS NULL OR is_deleted = 0)
            """,
            (
                data.get("type"),
                data.get("refValue1"),
                data.get("refValue2"),
                data.get("metric"),
                _date_only(data.get("dateOfObservation")) if data.get("dateOfObservation") else None,
                data.get("notes"),
                record_id,
                patient_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        cur.execute("SELECT * FROM Vitalsign WHERE id = %s", (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_immunization(patient_id: str, record_id: int, data: dict) -> Optional[dict]:
    """Update an Immunization row. Returns updated row or None if not found/owned."""
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE Immunization
            SET vaccineName     = COALESCE(%s, vaccineName),
                vaccinationDate = COALESCE(%s, vaccinationDate),
                notes           = COALESCE(%s, notes)
            WHERE id = %s AND patientId = %s AND (is_deleted IS NULL OR is_deleted = 0)
            """,
            (
                data.get("vaccineName"),
                _date_only(data.get("vaccinationDate")) if data.get("vaccinationDate") else None,
                data.get("notes"),
                record_id,
                patient_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        cur.execute("SELECT * FROM Immunization WHERE id = %s", (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_procedure(patient_id: str, record_id: int, data: dict) -> Optional[dict]:
    """Update a Procedures row. Returns updated row or None if not found/owned."""
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE Procedures
            SET procedureName = COALESCE(%s, procedureName),
                status        = COALESCE(%s, status),
                startDate     = COALESCE(%s, startDate),
                endDate       = COALESCE(%s, endDate),
                reason        = COALESCE(%s, reason),
                notes         = COALESCE(%s, notes)
            WHERE id = %s AND patientId = %s
              AND (is_deleted IS NULL OR is_deleted != 'Y')
            """,
            (
                data.get("procedureName"),
                data.get("status", "").upper() if data.get("status") else None,
                _date_only(data.get("startDate")) if data.get("startDate") else None,
                _date_only(data.get("endDate")) if data.get("endDate") else None,
                data.get("reason"),
                data.get("notes"),
                record_id,
                patient_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        cur.execute("SELECT * FROM Procedures WHERE id = %s", (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_condition(patient_id: str, record_id: int, data: dict) -> Optional[dict]:
    """Update a MedicalCondition row. Returns updated row or None if not found/owned."""
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE MedicalCondition
            SET conditionName = COALESCE(%s, conditionName),
                status        = COALESCE(%s, status),
                startDate     = COALESCE(%s, startDate),
                endDate       = COALESCE(%s, endDate),
                notes         = COALESCE(%s, notes)
            WHERE id = %s AND patientId = %s
              AND (is_deleted IS NULL OR is_deleted != 'Y')
            """,
            (
                data.get("conditionName"),
                data.get("status", "").upper() if data.get("status") else None,
                _date_only(data.get("startDate")) if data.get("startDate") else None,
                _date_only(data.get("endDate")) if data.get("endDate") else None,
                data.get("notes"),
                record_id,
                patient_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        cur.execute("SELECT * FROM MedicalCondition WHERE id = %s", (record_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ── Allergy Operations ─────────────────────────────────────────────────────────

def _build_raw_resource(patient_id: str, allergy_id: str, data: dict) -> dict:
    substance = data.get("substance", "")
    status = (data.get("status") or "active").lower()
    criticality = (data.get("criticality") or "low").lower()
    category = (data.get("category") or "medication").lower()
    reaction = data.get("reaction")
    onset = data.get("onsetDate") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    status_code = status if status in ("active", "inactive", "resolved") else "active"
    status_display = status_code.capitalize()

    raw = {
        "resourceType": "AllergyIntolerance",
        "id": str(allergy_id),
        "patient": {"reference": f"Patient/{patient_id}"},
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                    "code": status_code,
                    "display": status_display,
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                    "code": "confirmed",
                    "display": "Confirmed",
                }
            ]
        },
        "type": "allergy",
        "criticality": criticality,
        "category": [category],
        "code": {"text": substance},
        "onsetDateTime": str(onset),
    }
    if reaction:
        raw["reaction"] = [{"manifestation": [{"text": reaction}]}]
    if data.get("notes"):
        raw["note"] = [{"text": data["notes"]}]
    return raw


def _mysql_row_to_allergy_dict(row: dict) -> Optional[dict]:
    if not row:
        return None

    allergy_id = str(row.get("id"))
    patient_id = str(row.get("patientId") or row.get("patient_id") or "")
    substance = row.get("substance") or row.get("name") or ""
    severity = row.get("severity") or row.get("criticality") or "low"
    category = row.get("category") or "medication"
    status = row.get("status") or "active"

    start_date = row.get("startDate") or row.get("start_date") or row.get("onset") or ""
    if isinstance(start_date, (datetime, date)):
        start_date = start_date.strftime("%Y-%m-%d")

    notes = row.get("notes") or ""

    sev_upper = normalize_allergy_severity(severity) or "MILD"
    criticality = allergy_fhir_criticality(sev_upper)

    cat_lower = str(category).lower()
    stat_lower = str(status).lower()

    raw_resource = _build_raw_resource(
        patient_id,
        allergy_id,
        {
            "substance": substance,
            "criticality": criticality,
            "category": cat_lower,
            "status": stat_lower,
            "onsetDate": str(start_date),
            "notes": notes,
        },
    )

    return {
        "id": allergy_id,
        "patient_id": patient_id,
        "substance": substance,
        "criticality": criticality,
        "category": cat_lower,
        "status": stat_lower,
        "onset_date": str(start_date),
        "sort_date": str(start_date),
        "notes": notes,
        "source": row.get("source") or "manual_entry",
        "raw_resource": raw_resource,
    }


def find_existing_allergy(patient_id: str, substance: str, category: str = None):
    substance_clean = (substance or "").strip()
    if not substance_clean:
        return None

    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        if category:
            cur.execute(
                """
                SELECT *
                FROM Allergies
                WHERE patientId = %s
                  AND LOWER(TRIM(substance)) = LOWER(TRIM(%s))
                  AND LOWER(TRIM(category)) = LOWER(TRIM(%s))
                  AND (is_deleted IS NULL OR is_deleted != 'Y')
                LIMIT 1
                """,
                (patient_id, substance_clean, category),
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM Allergies
                WHERE patientId = %s
                  AND LOWER(TRIM(substance)) = LOWER(TRIM(%s))
                  AND (is_deleted IS NULL OR is_deleted != 'Y')
                LIMIT 1
                """,
                (patient_id, substance_clean),
            )
        row = cur.fetchone()
        return _mysql_row_to_allergy_dict(row) if row else None


def _compose_notes(data: dict) -> str:
    """Merge notes + reaction so OCR reaction text is not dropped (no reaction column)."""
    notes = (data.get("notes") or "").strip()
    reaction = (data.get("reaction") or "").strip()
    if reaction and reaction.lower() not in notes.lower():
        notes = f"{notes}\nReaction: {reaction}".strip() if notes else f"Reaction: {reaction}"
    return notes


def create_allergy(patient_id: str, data: dict) -> dict:
    substance = (data.get("substance") or data.get("name") or "").strip()
    category = (data.get("category") or "medication").upper()
    existing = find_existing_allergy(patient_id, substance)
    if existing:
        raise DuplicateClinicalRecordError(
            f"Allergy '{substance}' already exists for patient {patient_id}",
            existing_record_id=str(existing["id"]),
        )
    severity = normalize_allergy_severity(
        data.get("severity") or data.get("criticality") or "MILD"
    ) or "MILD"
    status = (data.get("status") or "active").upper()
    source = data.get("source", "manual_entry")
    onset_date = data.get("onsetDate") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    notes = _compose_notes(data)
    reaction = (data.get("reaction") or "").strip()

    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO Allergies (
                patientId,
                substance,
                allergyType,
                severity,
                category,
                startDate,
                status,
                notes,
                is_deleted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'N')
            """,
            (
                patient_id,
                substance,
                "ALLERGY",
                severity,
                category,
                onset_date[:10] if len(onset_date) >= 10 else onset_date,
                status,
                notes,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid

        cur.execute("SELECT * FROM Allergies WHERE id = %s", (new_id,))
        row = cur.fetchone()
        res = _mysql_row_to_allergy_dict(row)
        res["source"] = source
        if reaction:
            res["raw_resource"] = _build_raw_resource(
                patient_id,
                str(new_id),
                {
                    "substance": substance,
                    "criticality": allergy_fhir_criticality(severity),
                    "category": category.lower(),
                    "status": status.lower(),
                    "onsetDate": onset_date[:10] if len(onset_date) >= 10 else onset_date,
                    "notes": notes,
                    "reaction": reaction,
                },
            )
        return res


def update_allergy(patient_id: str, record_id: int, data: dict) -> Optional[dict]:
    """Update an Allergies row. Returns updated row dict or None if not found/owned."""
    allergy_id = str(record_id)
    substance = data.get("substance", "")
    severity = normalize_allergy_severity(
        data.get("severity") or data.get("criticality") or "MILD"
    ) or "MILD"
    category = (data.get("category") or "medication").upper()
    status = (data.get("status") or "active").upper()
    onset_date = data.get("onsetDate") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    notes = _compose_notes(data)

    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE Allergies
            SET substance = %s,
                severity = %s,
                category = %s,
                startDate = %s,
                status = %s,
                notes = %s
            WHERE id = %s AND patientId = %s
              AND (is_deleted IS NULL OR is_deleted != 'Y')
            """,
            (
                substance,
                severity,
                category,
                onset_date[:10] if len(onset_date) >= 10 else onset_date,
                status,
                notes,
                allergy_id,
                patient_id,
            ),
        )
        conn.commit()

        if cur.rowcount == 0:
            return None

        cur.execute("SELECT * FROM Allergies WHERE id = %s", (allergy_id,))
        row = cur.fetchone()
        return _mysql_row_to_allergy_dict(row) if row else None

