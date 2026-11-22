import logging
from .celery_app import celery_app
from .processing import reap_stale_jobs, run_job

log = logging.getLogger("reel.worker")


@celery_app.task(name="reel.process_job")
def process_job(job_id: int) -> str:
    return run_job(job_id)


@celery_app.task(name="reel.reap_stale_jobs")
def reap_stale_jobs_task() -> int:
    try:
        return reap_stale_jobs()
    except Exception:  # e.g. migrations not applied yet; try again on the next tick
        log.exception("Stale-job check failed")
        return 0
