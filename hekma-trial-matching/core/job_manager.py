from repositories import matching_jobs_repo


class JobManager:
    """
    DB-backed job stage updates (same contract as trialgpt file-based JobManager).
    """

    def __init__(self, base_dir=None):
        # base_dir kept for backward compatibility with legacy workflows.
        self.base_dir = base_dir

    def update_stage(self, job_id, stage, status, current_item=None, index=None, total=None):
        matching_jobs_repo.update_stage(
            job_id=job_id,
            stage=stage,
            stage_status=status,
            current_item=current_item,
            index=index,
            total=total,
        )

    def mark_running(self, job_id):
        matching_jobs_repo.update_overall_status(job_id, "RUNNING")

    def mark_completed(self, job_id):
        matching_jobs_repo.mark_completed(job_id)

    def fail_job(self, job_id, error, stage=None):
        matching_jobs_repo.fail_job(job_id, error, stage)

    def cancel_job(self, job_id):
        matching_jobs_repo.cancel_job(job_id)

    def is_cancelled(self, job_id):
        job = matching_jobs_repo.get_job(job_id)
        if not job:
            return False
        return job.get("status") == "CANCELLED"

    def get_job(self, job_id):
        job = matching_jobs_repo.get_job(job_id)
        if not job:
            raise FileNotFoundError("Job not found")
        return job

    def compute_progress(self, job):
        stages = [
            job.get("compose_status"),
            job.get("retrieve_status"),
            job.get("evaluate_status"),
            job.get("rank_status"),
        ]

        total = len(stages)
        done = sum(1 for s in stages if s == "COMPLETED")

        return int((done / total) * 100)
