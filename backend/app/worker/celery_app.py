import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_timeout = max(30, int(os.getenv("JOB_TIMEOUT_SECONDS", "900")))

celery_app = Celery("reel", broker=REDIS_URL, include=["app.worker.tasks"])
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], timezone="UTC", enable_utc=True,
    task_ignore_result=True,                 # job state lives in PostgreSQL, not in Redis
    task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    task_soft_time_limit=_timeout, task_time_limit=_timeout + 60,
    broker_connection_timeout=2, broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": _timeout + 300},
    # Tests/dev without Redis: run tasks inline in the calling process.
    task_always_eager=os.getenv("CELERY_EAGER", "").lower() in {"1", "true", "yes"},
    beat_schedule={"reap-stale-jobs": {"task": "reel.reap_stale_jobs", "schedule": 60.0}},
)
