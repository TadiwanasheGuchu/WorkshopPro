"""Background tasks. Business logic lives in services; tasks only add retry policy."""

import logging

from app.integrations.delivery import TransientDeliveryError
from app.services import notifications
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

MAX_RETRIES = notifications.MAX_ATTEMPTS - 1


@celery_app.task(name="notifications.send", bind=True, max_retries=MAX_RETRIES)
def send_notification(self, notification_id: str, link: str | None = None) -> None:  # type: ignore[no-untyped-def]
    final = self.request.retries >= MAX_RETRIES
    try:
        notifications.deliver(notification_id, link, final_attempt=final)
    except TransientDeliveryError as exc:
        # 30s, 1m, 2m, 4m, 8m ...
        raise self.retry(exc=exc, countdown=30 * 2**self.request.retries) from exc


@celery_app.task(name="notifications.requeue_stale")
def requeue_stale_notifications() -> int:
    count = notifications.requeue_stale()
    if count:
        logger.info("notifications_requeued", extra={"count": count})
    return count


@celery_app.task(name="reminders.service_due")
def send_service_reminders() -> int:
    from app.services import appointment_requests

    count = appointment_requests.send_service_reminders()
    if count:
        logger.info("service_reminders_sent", extra={"count": count})
    return count
