from utils.pg_util import pg_transaction


# -------- GET ALL PATIENT IDS --------
def get_all_mimic_patient_ids():
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT DISTINCT patient_id
            FROM mimic_patient
            WHERE patient_id IS NOT NULL
        """)

        rows = cursor.fetchall()

    return [r["patient_id"] if isinstance(r, dict) else r[0] for r in rows]


# -------- PATIENT --------
def get_mimic_patient(patient_id):
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT data
            FROM mimic_patient
            WHERE patient_id = %s
            LIMIT 1
        """, (patient_id,))

        row = cursor.fetchone()

    if not row:
        return None

    data = row["data"] if isinstance(row, dict) else row[0]
    return {"data": data}


# -------- CONDITIONS --------
def get_mimic_conditions(patient_id):
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT data FROM mimic_condition WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_condition_ed WHERE patient_id = %s
        """, (patient_id, patient_id))

        rows = cursor.fetchall()

    return [{"data": r["data"] if isinstance(r, dict) else r[0]} for r in rows]


# -------- MEDICATIONS --------
def get_mimic_medications(patient_id):
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT data FROM mimic_medication_request WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_medication_administration WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_medication_dispense WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_medication_dispense_ed WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_medication_statement_ed WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_medication_administration_icu WHERE patient_id = %s
        """, (patient_id, patient_id, patient_id, patient_id, patient_id, patient_id))

        rows = cursor.fetchall()

    return [{"data": r["data"] if isinstance(r, dict) else r[0]} for r in rows]


# -------- PROCEDURES --------
def get_mimic_procedures(patient_id):
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT data FROM mimic_procedure WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_procedure_icu WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_procedure_ed WHERE patient_id = %s
        """, (patient_id, patient_id, patient_id))

        rows = cursor.fetchall()

    return [{"data": r["data"] if isinstance(r, dict) else r[0]} for r in rows]


# -------- OBSERVATIONS --------
def get_mimic_observations(patient_id):
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT data FROM mimic_observation_labevents WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_observation_vital_signs_ed WHERE patient_id = %s
        """, (patient_id, patient_id))

        rows = cursor.fetchall()

    return [{"data": r["data"] if isinstance(r, dict) else r[0]} for r in rows]


# -------- ENCOUNTERS --------
def get_mimic_encounters(patient_id):
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT data FROM mimic_encounter WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_encounter_ed WHERE patient_id = %s
            UNION ALL
            SELECT data FROM mimic_encounter_icu WHERE patient_id = %s
        """, (patient_id, patient_id, patient_id))

        rows = cursor.fetchall()

    return [{"data": r["data"] if isinstance(r, dict) else r[0]} for r in rows]



def get_mimic_patient_ids_batch(limit, offset):
    with pg_transaction() as (_, cursor):

        cursor.execute("""
            SELECT patient_id
            FROM mimic_patient
            WHERE patient_id IS NOT NULL
            ORDER BY patient_id
            LIMIT %s OFFSET %s
        """, (limit, offset))

        rows = cursor.fetchall()

    return [r["patient_id"] if isinstance(r, dict) else r[0] for r in rows]