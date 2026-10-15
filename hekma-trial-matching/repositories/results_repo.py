from utils.pg_util import pg_transaction


def fetch_job_results(job_id):
    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT fr.query_id,
                fr.candidate_id,
                fr.rank_position,
                fr.final_score,
                ar.relevance_score_r AS "relevance_score_R",
                ar.eligibility_score_e AS "eligibility_score_E",
                mr.inclusion_results,
                mr.exclusion_results,
                mj.parameters
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

            LEFT JOIN matching_jobs mj
                ON fr.job_id = mj.job_id

            WHERE fr.job_id = %s
            ORDER BY fr.rank_position ASC
            """,
            (job_id,),
        )

        return cur.fetchall()
