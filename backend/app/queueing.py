"""API-side access to the job queue. Importing Celery lazily keeps the API importable without a broker."""
import logging

log = logging.getLogger("reel.queue")


class QueueUnavailable(Exception):
    pass


def enqueue_job(job_id: int) -> None:
    from .worker.tasks import process_job
    try:
        process_job.apply_async(args=[job_id], retry=True, retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5})
    except Exception as exc:
        log.error("Could not enqueue job %s: %s", job_id, exc)
        raise QueueUnavailable(str(exc)) from exc


def queue_status() -> dict:
    from .worker.celery_app import celery_app
    if celery_app.conf.task_always_eager:
        return {"mode": "inline", "broker_ok": True, "workers": 0, "detail": "Jobs run inside the API process (CELERY_EAGER is on). Not for production."}
    try:
        replies = celery_app.control.inspect(timeout=1.0).ping() or {}
    except Exception:
        return {"mode": "redis", "broker_ok": False, "workers": 0, "detail": "The job queue (Redis) is not reachable."}
    return {"mode": "redis", "broker_ok": True, "workers": len(replies), "detail": None if replies else "No worker is running. Queued jobs will wait until one starts."}
