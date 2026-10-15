from utils.pg_util import pg_transaction


def _coerce_score(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def insert_aggregation_result(
    job_id,
    flow_type,
    query_id,
    candidate_id,
    relevance_score,
    eligibility_score,
    relevance_explanation,
    eligibility_explanation,
):
    with pg_transaction(dict_cursor=False) as (_, cur):
        cur.execute(
            """
            INSERT INTO aggregation_results (
                job_id,
                flow_type,
                query_id,
                candidate_id,
                relevance_score_R,
                eligibility_score_E,
                relevance_explanation,
                eligibility_explanation
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                job_id,
                flow_type,
                query_id,
                candidate_id,
                _coerce_score(relevance_score),
                _coerce_score(eligibility_score),
                relevance_explanation,
                eligibility_explanation,
            ),
        )
