import json
from datetime import datetime

from repositories.matching_pipeline_schema import ensure_matching_pipeline_tables
from utils.pg_util import pg_transaction

# Control flags that must not prevent returning a cached COMPLETED job.
_CACHE_IGNORE_PARAMETER_KEYS = frozenset({"force_rerun"})


def canonical_job_parameters(parameters) -> dict:
    """
    Build the cache fingerprint for a job request.

    Drops force_rerun so force_rerun=false can reuse a job that was started with
    force_rerun=true (identical matching inputs).
    """
    if not isinstance(parameters, dict):
        return {}
    return {
        key: value
        for key, value in parameters.items()
        if key not in _CACHE_IGNORE_PARAMETER_KEYS
    }


def create_job(
    job_id,
    flow_type,
    requested_user_id,
    user_type,
    query_id,
    parameters,
):
    ensure_matching_pipeline_tables()
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            INSERT INTO matching_jobs (
                job_id,
                flow_type,
                requested_user_id,
                user_type,
                query_id,
                parameters,
                status,
                compose_status,
                retrieve_status,
                evaluate_status,
                rank_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                job_id,
                flow_type,
                requested_user_id,
                user_type,
                query_id,
                json.dumps(parameters),
                "STARTED",
                "PENDING",
                "PENDING",
                "PENDING",
                "PENDING",
            ),
        )


def update_stage(job_id, stage, stage_status, current_item=None, index=None, total=None):
    stage_column_map = {
        "compose": "compose_status",
        "retrieve": "retrieve_status",
        "evaluate": "evaluate_status",
        "rank": "rank_status",
    }

    if stage not in stage_column_map:
        raise ValueError(f"Invalid stage: {stage}")

    column = stage_column_map[stage]

    with pg_transaction() as (_, cur):

        stage_meta_fragment = {}

        if stage_status == "RUNNING":
            stage_meta_fragment["started_at"] = datetime.utcnow().isoformat()

        if stage_status in ["COMPLETED", "FAILED"]:
            stage_meta_fragment["completed_at"] = datetime.utcnow().isoformat()
        if current_item is not None:
            stage_meta_fragment["current_item"] = current_item

        if index is not None:
            stage_meta_fragment["current_item_index"] = index

        if total is not None:
            stage_meta_fragment["total_items"] = total

        cur.execute(
            f"""
            UPDATE matching_jobs
            SET {column} = %s,
                updated_at = NOW(),
                stage_meta = jsonb_set(
                    COALESCE(stage_meta, '{{}}'::jsonb),
                    %s::text[],
                    COALESCE(stage_meta->%s, '{{}}'::jsonb) || %s::jsonb,
                    true
                )
            WHERE job_id = %s
            """,
            (
                stage_status,
                [stage],
                stage,
                json.dumps(stage_meta_fragment),
                job_id,
            ),
        )

        if stage_status == "RUNNING":
            cur.execute(
                """
                UPDATE matching_jobs
                SET status = 'RUNNING',
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )

        if stage_status == "FAILED":
            cur.execute(
                """
                UPDATE matching_jobs
                SET status = 'FAILED',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )

        if stage == "rank" and stage_status == "COMPLETED":
            cur.execute(
                """
                UPDATE matching_jobs
                SET status = 'COMPLETED',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )


def cancel_job(job_id):
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            UPDATE matching_jobs
            SET status = 'CANCELLED',
                updated_at = NOW()
            WHERE job_id = %s
            """,
            (job_id,),
        )


def fail_job(job_id, error, stage=None):
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            UPDATE matching_jobs
            SET status = 'FAILED',
                error = %s,
                error_stage = %s,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE job_id = %s
            """,
            (str(error), stage, job_id),
        )


def get_job(job_id):
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT * FROM matching_jobs WHERE job_id = %s",
            (job_id,),
        )
        return cur.fetchone()


def get_jobs_by_query(query_id, flow_type):
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT *
            FROM matching_jobs
            WHERE query_id = %s
              AND flow_type = %s
            ORDER BY created_at DESC
            """,
            (query_id, flow_type),
        )
        return cur.fetchall()


def get_jobs_by_user(requested_user_id):
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT *
            FROM matching_jobs
            WHERE requested_user_id = %s
            ORDER BY created_at DESC
            """,
            (requested_user_id,),
        )
        return cur.fetchall()


def update_overall_status(job_id, status):
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            UPDATE matching_jobs
            SET status = %s,
                updated_at = NOW()
            WHERE job_id = %s
            """,
            (status, job_id),
        )


def mark_completed(job_id):
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            UPDATE matching_jobs
            SET status = 'COMPLETED',
                completed_at = NOW(),
                updated_at = NOW()
            WHERE job_id = %s
            """,
            (job_id,),
        )


def get_job_status(job_id: str):
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT
                job_id,
                flow_type,
                requested_user_id,
                user_type,
                query_id,
                parameters,
                status,
                compose_status,
                retrieve_status,
                evaluate_status,
                rank_status,
                stage_meta,
                error,
                error_stage,
                created_at,
                updated_at,
                completed_at
            FROM matching_jobs
            WHERE job_id = %s
            """,
            (job_id,),
        )

        return cur.fetchone()


def find_completed_job_by_parameters(query_id, flow_type, parameters):
    """
    Return the latest COMPLETED job_id with the same cache fingerprint.

    Compares parameters with force_rerun removed on both sides so callers can
    set force_rerun=false and still hit a prior force_rerun=true run.
    """
    fingerprint = canonical_job_parameters(parameters)
    ensure_matching_pipeline_tables()
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT job_id
            FROM matching_jobs
            WHERE query_id = %s
              AND flow_type = %s
              AND (parameters - 'force_rerun') = %s::jsonb
              AND status = 'COMPLETED'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                query_id,
                flow_type,
                json.dumps(fingerprint),
            ),
        )

        row = cur.fetchone()

        if row:
            return row["job_id"]

        return None
