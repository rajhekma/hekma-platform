import json
from utils.pg_util import pg_transaction


def insert_matching_result(
    job_id,
    flow_type,
    query_id,
    candidate_id,
    inclusion_results,
    exclusion_results,
):
    with pg_transaction(dict_cursor=False) as (_, cur):
        cur.execute(
            """
            INSERT INTO matching_results (
                job_id,
                flow_type,
                query_id,
                candidate_id,
                inclusion_results,
                exclusion_results
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                job_id,
                flow_type,
                query_id,
                candidate_id,
                json.dumps(inclusion_results),
                json.dumps(exclusion_results),
            ),
        )
