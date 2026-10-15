from utils.pg_util import pg_transaction


def insert_retrieval_results(job_id, flow_type, qid2nctids):
    with pg_transaction(dict_cursor=False) as (_, cur):

        for query_id, nctids in qid2nctids.items():

            for rank, candidate_id in enumerate(nctids, start=1):

                cur.execute(
                    """
                    INSERT INTO retrieval_results (
                        job_id,
                        flow_type,
                        query_id,
                        candidate_id,
                        rank_position
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        flow_type,
                        query_id,
                        candidate_id,
                        rank,
                    ),
                )
