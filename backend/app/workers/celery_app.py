"""Celery application (Redis broker). Run the worker with:

    celery -A app.workers.celery_app worker --beat --loglevel=info

`--beat` runs the periodic schedule inside the worker, which suits a single-instance
installation. Run one worker with --beat only; add more workers without it.
"""

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

celery_app = Celery("workshoppro", broker=str(settings.redis_url), include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "requeue-stale-notifications": {
            "task": "notifications.requeue_stale",
            "schedule": 300.0,
        },
        # Hourly is enough for day-based reminders; each vehicle and due date is sent once.
        "service-reminders": {
            "task": "reminders.service_due",
            "schedule": 3600.0,
        },
    },
)
