from utils.pg_util import pg_transaction


def insert_final_ranking(
    job_id,
    flow_type,
    query_id,
    candidate_id,
    final_score,
    rank_position,
):
    with pg_transaction(dict_cursor=False) as (_, cur):
        cur.execute(
            """
            INSERT INTO final_ranking (
                job_id,
                flow_type,
                query_id,
                candidate_id,
                final_score,
                rank_position
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                job_id,
                flow_type,
                query_id,
                candidate_id,
                final_score,
                rank_position,
            ),
        )
