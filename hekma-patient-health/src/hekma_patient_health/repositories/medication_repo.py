from ..awsutils.postgresql_utils import pg_transaction
from ..utils.prescription_dates import normalize_prescription_date
from .medication_schema import ensure_medication_daily_count_schema


def create_medication(patient_id, data):
    """Insert a medication row; ensures schema columns exist first."""
    ensure_medication_daily_count_schema()
    doctor_name = data.get("doctorName") if "doctorName" in data else data.get("doctor_name")
    facility_name = data.get("facilityName") if "facilityName" in data else data.get("facility_name")
    raw_date = data.get("prescriptionDate") if "prescriptionDate" in data else data.get("prescription_date")
    prescription_date = normalize_prescription_date(raw_date)
    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            INSERT INTO medications (
                patient_id,
                name,
                dosage,
                how_much_to_take,
                strength,
                medication_type,
                frequency,
                start_date,
                end_date,
                instructions,
                is_reminder_enabled,
                status,
                notes,
                prescription_id,
                daily_target_count,
                doctor_name,
                facility_name,
                prescription_date
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                patient_id,
                data["name"],
                data["dosage"],
                data.get("howMuchToTake", ""),
                data.get("strength", ""),
                data.get("medicationType"),
                data["frequency"],
                data.get("startDate"),
                data.get("endDate"),
                data["instructions"],
                data["isReminderEnabled"],
                data["status"],
                data["notes"],
                data.get("prescriptionId"),
                data.get("dailyTargetCount"),
                doctor_name,
                facility_name,
                prescription_date,
            ),
        )

        row = cur.fetchone()
        if row and row.get("prescription_id"):
            cur.execute(
                "SELECT prescriber_name, prescription_date, extracted_data FROM prescriptions WHERE id = %s",
                (row["prescription_id"],),
            )
            p_row = cur.fetchone()
            if p_row:
                if not row.get("doctor_name") and p_row.get("prescriber_name"):
                    row["doctor_name"] = p_row["prescriber_name"]
                if not row.get("prescription_date") and p_row.get("prescription_date"):
                    row["prescription_date"] = p_row["prescription_date"]
                if not row.get("facility_name") and isinstance(p_row.get("extracted_data"), dict):
                    row["facility_name"] = p_row["extracted_data"].get("clinic")
        return row


def set_medication_hekma_id(medication_id: int, hekma_id: str) -> None:
    """Link an adherence medication row to its FHIR MedicationRequest hekma_id."""
    ensure_medication_daily_count_schema()
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            UPDATE medications
            SET hekma_id = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (hekma_id, medication_id),
        )


def update_medication(medication_id, data):
    """Update medication fields; leave daily_target_count unchanged when omitted."""
    ensure_medication_daily_count_schema()
    doctor_name = data.get("doctorName") if "doctorName" in data else data.get("doctor_name")
    facility_name = data.get("facilityName") if "facilityName" in data else data.get("facility_name")
    raw_date = data.get("prescriptionDate") if "prescriptionDate" in data else data.get("prescription_date")
    prescription_date = normalize_prescription_date(raw_date)
    with pg_transaction(dict_cursor=True) as (_, cur):
        # Avoid wiping count targets when clients omit the optional field on PUT.
        if "dailyTargetCount" in data:
            cur.execute(
                """
                UPDATE medications
                SET
                    name=%s,
                    dosage=%s,
                    how_much_to_take=%s,
                    strength=%s,
                    medication_type=%s,
                    frequency=%s,
                    start_date=%s,
                    end_date=%s,
                    instructions=%s,
                    is_reminder_enabled=%s,
                    status=%s,
                    notes=%s,
                    prescription_id=%s,
                    daily_target_count=%s,
                    doctor_name=%s,
                    facility_name=%s,
                    prescription_date=%s,
                    updated_at=NOW()
                WHERE id=%s
                RETURNING *
                """,
                (
                    data["name"],
                    data["dosage"],
                    data.get("howMuchToTake", ""),
                    data.get("strength", ""),
                    data.get("medicationType"),
                    data["frequency"],
                    data.get("startDate"),
                    data.get("endDate"),
                    data["instructions"],
                    data["isReminderEnabled"],
                    data["status"],
                    data["notes"],
                    data.get("prescriptionId"),
                    data.get("dailyTargetCount"),
                    doctor_name,
                    facility_name,
                    prescription_date,
                    medication_id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE medications
                SET
                    name=%s,
                    dosage=%s,
                    how_much_to_take=%s,
                    strength=%s,
                    medication_type=%s,
                    frequency=%s,
                    start_date=%s,
                    end_date=%s,
                    instructions=%s,
                    is_reminder_enabled=%s,
                    status=%s,
                    notes=%s,
                    prescription_id=%s,
                    doctor_name=%s,
                    facility_name=%s,
                    prescription_date=%s,
                    updated_at=NOW()
                WHERE id=%s
                RETURNING *
                """,
                (
                    data["name"],
                    data["dosage"],
                    data.get("howMuchToTake", ""),
                    data.get("strength", ""),
                    data.get("medicationType"),
                    data["frequency"],
                    data.get("startDate"),
                    data.get("endDate"),
                    data["instructions"],
                    data["isReminderEnabled"],
                    data["status"],
                    data["notes"],
                    data.get("prescriptionId"),
                    doctor_name,
                    facility_name,
                    prescription_date,
                    medication_id,
                ),
            )

        row = cur.fetchone()
        if row and row.get("prescription_id"):
            cur.execute(
                "SELECT prescriber_name, prescription_date, extracted_data FROM prescriptions WHERE id = %s",
                (row["prescription_id"],),
            )
            p_row = cur.fetchone()
            if p_row:
                if not row.get("doctor_name") and p_row.get("prescriber_name"):
                    row["doctor_name"] = p_row["prescriber_name"]
                if not row.get("prescription_date") and p_row.get("prescription_date"):
                    row["prescription_date"] = p_row["prescription_date"]
                if not row.get("facility_name") and isinstance(p_row.get("extracted_data"), dict):
                    row["facility_name"] = p_row["extracted_data"].get("clinic")
        return row


def delete_medication(medication_id):

    with pg_transaction() as (_, cur):

        cur.execute(
            """
            DELETE FROM medications
            WHERE id=%s
            """,
            (medication_id,),
        )


def get_medications_by_patient(patient_id):
    """List medications for a patient; ensures schema columns exist first."""
    ensure_medication_daily_count_schema()

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT
                m.*,
                COALESCE(m.doctor_name, p.prescriber_name) AS doctor_name,
                COALESCE(m.facility_name, p.extracted_data->>'clinic') AS facility_name,
                COALESCE(m.prescription_date, p.prescription_date) AS prescription_date
            FROM medications m
            LEFT JOIN prescriptions p ON m.prescription_id = p.id
            WHERE m.patient_id=%s
              AND m.archived_at IS NULL
            ORDER BY m.created_at DESC
            """,
            (patient_id,),
        )

        return cur.fetchall()


def get_medication(medication_id):
    """Load one medication by id; ensures schema columns exist first."""
    ensure_medication_daily_count_schema()

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT
                m.*,
                COALESCE(m.doctor_name, p.prescriber_name) AS doctor_name,
                COALESCE(m.facility_name, p.extracted_data->>'clinic') AS facility_name,
                COALESCE(m.prescription_date, p.prescription_date) AS prescription_date
            FROM medications m
            LEFT JOIN prescriptions p ON m.prescription_id = p.id
            WHERE m.id=%s
            """,
            (medication_id,),
        )

        return cur.fetchone()


def medication_belongs_to_patient(medication_id, patient_id):

    medication = get_medication(medication_id)
    return medication is not None and medication.get("patient_id") == patient_id
