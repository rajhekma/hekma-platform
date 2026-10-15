import uuid

def generate_job_id():
    return uuid.uuid4().hex

def is_job_cancelled(job_manager, job_id):
    return job_manager.is_cancelled(job_id)

def compute_progress(job):
    total = len(job["stages"])
    done = sum(1 for s in job["stages"].values() if s == "COMPLETED")
    return int((done / total) * 100)
