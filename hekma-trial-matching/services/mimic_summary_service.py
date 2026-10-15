from repositories.mimic_repo import *
from repositories.mimic_compose_repo import upsert_mimic_summary

from services.mimic_summary_builder import build_mimic_structured_json
from services.mimic_summary_llm_service import generate_mimic_summary

from datetime import datetime


def process_mimic_summaries(patient_id=None):

    batch_size = 50
    offset = 0
    total_processed = 0

    while True:

        if patient_id:
            ids = [patient_id]
        else:
            ids = get_mimic_patient_ids_batch(batch_size, offset)

        if not ids:
            break

        print(f"Processing batch offset={offset}, size={len(ids)}")

        for pid in ids:

            try:
                patient = get_mimic_patient(pid)
                if not patient:
                    continue

                conditions = get_mimic_conditions(pid)
                meds = get_mimic_medications(pid)
                procs = get_mimic_procedures(pid)
                obs = get_mimic_observations(pid)
                enc = get_mimic_encounters(pid)

                structured = build_mimic_structured_json(
                    patient, conditions, meds, procs, obs, enc
                )

                result = generate_mimic_summary(structured, patient_id=pid)

                upsert_mimic_summary(
                    pid,
                    result["summary_text"],
                    structured,
                    result["disease_list"],
                    datetime.utcnow()
                )

                total_processed += 1

            except Exception as e:
                print(f"Error processing {pid}: {e}")
                continue

        offset += batch_size

        if patient_id:
            break

    return {
        "status": "done",
        "total_processed": total_processed
    }