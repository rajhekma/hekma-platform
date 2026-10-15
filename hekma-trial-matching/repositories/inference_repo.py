from utils.pg_util import pg_corpus_transaction, pg_transaction
import logging

logger = logging.getLogger(__name__)
COMPOSE_READ_TABLE = "trialgpt_eligible_patients"
COMPOSE_ID_COLUMN = "subject_id"


def _preferred_llm_flag() -> bool:
    """Same llm mode P2T matching uses; default True if config cannot load."""
    try:
        from config.trial_gpt_ehr_config import get_trial_gpt_ehr_config

        return bool(get_trial_gpt_ehr_config().p2t_preferred_llm)
    except Exception:
        logger.exception("[INFERENCE] EHR config unavailable; defaulting llm=True")
        return True


def _nonempty_summary(row) -> str | None:
    if not row:
        return None
    text = row.get("summary_text") if isinstance(row, dict) else None
    if text is None:
        return None
    stripped = str(text).strip()
    return stripped or None


def _fetch_ehr_summary(cur, subject_id: str, llm: bool):
    cur.execute(
        """
        SELECT summary_text
        FROM trial_gpt_ehr
        WHERE subject_id = %s
          AND llm = %s
          AND summary_status = 'ready'
          AND summary_text IS NOT NULL
          AND BTRIM(summary_text) <> ''
        ORDER BY last_generated_at DESC NULLS LAST
        LIMIT 1
        """,
        (subject_id, llm),
    )
    return _nonempty_summary(cur.fetchone())


def _fetch_eligible_summary(cur, subject_id: str):
    cur.execute(
        f"""
        SELECT summary_text
        FROM {COMPOSE_READ_TABLE}
        WHERE {COMPOSE_ID_COLUMN} = %s
          AND summary_text IS NOT NULL
          AND BTRIM(summary_text) <> ''
        LIMIT 1
        """,
        (subject_id,),
    )
    return _nonempty_summary(cur.fetchone())


def fetch_patient_summary_for_inference(cur, subject_id: str) -> dict | None:
    """
    Load patient summary for nct/patient insight.

    Order matches how P2T actually runs today:
      1. trial_gpt_ehr at the preferred llm flag
      2. trial_gpt_ehr at the other llm flag (ready row still usable for evidence)
      3. trialgpt_eligible_patients (legacy cohort)

    Returns {"summary_text": str} or None.
    """
    if not subject_id or not str(subject_id).strip():
        return None

    subject_id = str(subject_id).strip()
    preferred = _preferred_llm_flag()
    other = not preferred

    text = _fetch_ehr_summary(cur, subject_id, preferred)
    if text:
        logger.info(
            "[INFERENCE] Patient summary source=trial_gpt_ehr llm=%s subject_id=%s",
            preferred,
            subject_id,
        )
        return {"summary_text": text}

    text = _fetch_ehr_summary(cur, subject_id, other)
    if text:
        logger.info(
            "[INFERENCE] Patient summary source=trial_gpt_ehr llm=%s (fallback) subject_id=%s",
            other,
            subject_id,
        )
        return {"summary_text": text}

    text = _fetch_eligible_summary(cur, subject_id)
    if text:
        logger.info(
            "[INFERENCE] Patient summary source=%s subject_id=%s",
            COMPOSE_READ_TABLE,
            subject_id,
        )
        return {"summary_text": text}

    logger.warning(
        "[INFERENCE] No patient summary in trial_gpt_ehr or %s | subject_id=%s",
        COMPOSE_READ_TABLE,
        subject_id,
    )
    return None


def _fetch_corpus_trial_row(nct_id):
    """Load trial criteria from the corpus database, separate from ranking tables."""
    with pg_corpus_transaction(dict_cursor=True) as (_, corpus_cur):
        corpus_cur.execute(
            """
            SELECT title,
                   inclusion_criteria,
                   exclusion_criteria
            FROM trialgpt_corpus
            WHERE nct_id = %s
            """,
            (nct_id,),
        )
        return corpus_cur.fetchone()


def fetch_nct_inference_data(job_id, nct_id):

    logger.info("[INFERENCE] Fetching NCT inference for job=%s, nct=%s", job_id, nct_id)

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT fr.query_id,
                   fr.final_score,
                   ar.relevance_score_R AS relevance_score_r,
                   ar.eligibility_score_E AS eligibility_score_e,
                   ar.relevance_explanation,
                   ar.eligibility_explanation,
                   mr.inclusion_results,
                   mr.exclusion_results
            FROM final_ranking fr
            LEFT JOIN aggregation_results ar
              ON fr.job_id = ar.job_id
             AND fr.flow_type = ar.flow_type
             AND fr.query_id = ar.query_id
             AND fr.candidate_id = ar.candidate_id
            LEFT JOIN matching_results mr
              ON fr.job_id = mr.job_id
             AND fr.flow_type = mr.flow_type
             AND fr.query_id = mr.query_id
             AND fr.candidate_id = mr.candidate_id
            WHERE fr.job_id = %s
              AND fr.candidate_id = %s
            """,
            (job_id, nct_id),
        )

        result = cur.fetchone()

        if not result:
            logger.warning("[INFERENCE] No ranking row found")
            return None

        patient_id = result["query_id"]

        trial_row = _fetch_corpus_trial_row(nct_id)
        patient_row = fetch_patient_summary_for_inference(cur, patient_id)

    return {
        "patient_id": patient_id,
        "final_score": result["final_score"],
        "relevance_score": result["relevance_score_r"],
        "eligibility_score": result["eligibility_score_e"],
        "relevance_explanation": result["relevance_explanation"],
        "eligibility_explanation": result["eligibility_explanation"],
        "inclusion_results": result["inclusion_results"],
        "exclusion_results": result["exclusion_results"],
        "trial_row": trial_row,
        "patient_row": patient_row,
    }


def fetch_patient_inference_data(job_id, patient_id):
    """
    T2P: query_id on final_ranking is nct_id; candidate_id is patient (subject) id.
    """

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT fr.query_id,
                fr.final_score,
                ar.relevance_score_R AS relevance_score_r,
                ar.eligibility_score_E AS eligibility_score_e,
                ar.relevance_explanation,
                ar.eligibility_explanation,
                mr.inclusion_results,
                mr.exclusion_results
            FROM final_ranking fr
            LEFT JOIN aggregation_results ar
            ON fr.job_id = ar.job_id
            AND fr.flow_type = ar.flow_type
            AND fr.query_id = ar.query_id
            AND fr.candidate_id = ar.candidate_id
            LEFT JOIN matching_results mr
            ON fr.job_id = mr.job_id
            AND fr.flow_type = mr.flow_type
            AND fr.query_id = mr.query_id
            AND fr.candidate_id = mr.candidate_id
            WHERE fr.job_id = %s
            AND fr.candidate_id = %s
            """,
            (job_id, patient_id),
        )

        result = cur.fetchone()

        if not result:
            return None

        nct_id = result["query_id"]

        trial_row = _fetch_corpus_trial_row(nct_id)
        patient_row = fetch_patient_summary_for_inference(cur, patient_id)

    return {
        "nct_id": nct_id,
        "final_score": result["final_score"],
        "relevance_score": result["relevance_score_r"],
        "eligibility_score": result["eligibility_score_e"],
        "relevance_explanation": result["relevance_explanation"],
        "eligibility_explanation": result["eligibility_explanation"],
        "inclusion_results": result["inclusion_results"],
        "exclusion_results": result["exclusion_results"],
        "trial_row": trial_row,
        "patient_row": patient_row,
    }
