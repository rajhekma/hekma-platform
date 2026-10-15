from repositories.mimic_repo import (
    get_mimic_patient,
    get_mimic_conditions,
    get_mimic_medications,
    get_mimic_procedures,
    get_mimic_observations,
    get_mimic_encounters,
)
from repositories.patient_summary_validation_repo import (
    get_mimic_summary_record,
    list_mimic_summary_patients,
    get_cached_validation,
    upsert_validation,
)
from services.mimic_summary_builder import build_mimic_structured_json
from services.patient_summary_validation_llm_service import run_llm_validation


def _build_patient_360_from_mimic(patient_id: str) -> dict:
    patient = get_mimic_patient(patient_id)
    if not patient:
        return {}

    return build_mimic_structured_json(
        patient,
        get_mimic_conditions(patient_id),
        get_mimic_medications(patient_id),
        get_mimic_procedures(patient_id),
        get_mimic_observations(patient_id),
        get_mimic_encounters(patient_id),
    )


def _rule_based_checks(summary_text: str, patient_360: dict, disease_list: list) -> dict:
    checks = []
    summary_lower = (summary_text or "").lower()

    patient = patient_360.get("patient") or {}
    gender = (patient.get("gender") or "").lower()
    if gender and gender not in summary_lower:
        checks.append(
            {
                "category": "demographics",
                "status": "warning",
                "message": "Patient gender is present in Patient 360 but not clearly reflected in the summary.",
                "evidence": f"gender={gender}",
            }
        )

    conditions = patient_360.get("conditions") or []
    if conditions and not any(
        (c.get("name") or "").lower() in summary_lower for c in conditions[:5]
    ):
        checks.append(
            {
                "category": "conditions",
                "status": "warning",
                "message": "None of the top structured conditions appear in the summary text.",
                "evidence": ", ".join(
                    (c.get("name") or "") for c in conditions[:3] if c.get("name")
                ),
            }
        )

    if not summary_text or not summary_text.strip():
        checks.append(
            {
                "category": "general",
                "status": "fail",
                "message": "Summary text is empty.",
                "evidence": None,
            }
        )

    if not patient_360:
        checks.append(
            {
                "category": "general",
                "status": "fail",
                "message": "Patient 360 structured data is unavailable.",
                "evidence": None,
            }
        )

    if disease_list and conditions:
        condition_names = {(c.get("name") or "").lower() for c in conditions}
        unmatched = [
            d for d in disease_list if d and d.lower() not in condition_names
        ]
        if len(unmatched) > max(2, len(disease_list) // 2):
            checks.append(
                {
                    "category": "diseases",
                    "status": "warning",
                    "message": "Several disease_list entries are not aligned with structured conditions.",
                    "evidence": ", ".join(unmatched[:5]),
                }
            )

    fail_count = sum(1 for c in checks if c["status"] == "fail")
    warn_count = sum(1 for c in checks if c["status"] == "warning")

    if fail_count:
        status = "fail"
        score = max(0, 50 - fail_count * 15)
    elif warn_count:
        status = "warning"
        score = max(60, 85 - warn_count * 8)
    else:
        status = "pass"
        score = 95

    return {
        "overall_status": status,
        "reliability_score": score,
        "summary": "Rule-based structural checks completed.",
        "checks": checks,
        "fabrications": [],
        "omissions": [],
        "validator": "rules",
    }


def _merge_validation(rule_result: dict, llm_result: dict) -> dict:
    status_rank = {"pass": 0, "warning": 1, "fail": 2}
    overall_status = rule_result["overall_status"]
    if status_rank[llm_result["overall_status"]] > status_rank[overall_status]:
        overall_status = llm_result["overall_status"]

    reliability_score = min(rule_result["reliability_score"], llm_result["reliability_score"])

    return {
        "overall_status": overall_status,
        "reliability_score": reliability_score,
        "summary": llm_result.get("summary") or rule_result.get("summary"),
        "checks": (rule_result.get("checks") or []) + (llm_result.get("checks") or []),
        "fabrications": llm_result.get("fabrications") or [],
        "omissions": llm_result.get("omissions") or [],
        "validators": ["rules", "llm"],
    }


def get_validation_context(patient_id: str, refresh_patient_360: bool = False):
    record = get_mimic_summary_record(patient_id)
    if not record:
        raise ValueError("Patient summary not found")

    patient_360 = record["structured_json"]
    if refresh_patient_360 or not patient_360:
        patient_360 = _build_patient_360_from_mimic(patient_id)

    cached = get_cached_validation(patient_id)

    return {
        "patient_id": patient_id,
        "summary_text": record["summary_text"],
        "disease_list": record["disease_list"],
        "patient_360": patient_360,
        "summary_updated_at": record["updated_at"],
        "last_validation": cached,
    }


def validate_patient_summary(
    patient_id: str,
    refresh_patient_360: bool = False,
    use_llm: bool = True,
    persist: bool = True,
):
    ctx = get_validation_context(patient_id, refresh_patient_360=refresh_patient_360)

    rule_result = _rule_based_checks(
        ctx["summary_text"],
        ctx["patient_360"],
        ctx["disease_list"],
    )

    if use_llm:
        llm_result = run_llm_validation(
            ctx["summary_text"],
            ctx["patient_360"],
            ctx["disease_list"],
            patient_id=patient_id,
        )
        validation = _merge_validation(rule_result, llm_result)
    else:
        validation = {**rule_result, "validators": ["rules"]}

    if persist:
        upsert_validation(
            patient_id,
            validation,
            validation["overall_status"],
            validation["reliability_score"],
        )

    return {
        "patient_id": patient_id,
        "summary_text": ctx["summary_text"],
        "disease_list": ctx["disease_list"],
        "patient_360": ctx["patient_360"],
        "summary_updated_at": ctx["summary_updated_at"],
        "validation": validation,
    }


def list_patients(limit: int = 50, offset: int = 0):
    listing = list_mimic_summary_patients(limit=limit, offset=offset)

    patient_ids = [p["patient_id"] for p in listing["patients"]]
    statuses = {}
    if patient_ids:
        from utils.pg_util import pg_transaction

        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT patient_id, overall_status, reliability_score, validated_at
                FROM patient_summary_validations
                WHERE patient_id = ANY(%s)
                """,
                (patient_ids,),
            )
            for row in cur.fetchall():
                statuses[row["patient_id"]] = {
                    "overall_status": row["overall_status"],
                    "reliability_score": row["reliability_score"],
                    "validated_at": row["validated_at"],
                }

    for patient in listing["patients"]:
        patient["validation_status"] = statuses.get(patient["patient_id"])

    return listing
