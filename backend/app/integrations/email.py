"""Email delivery adaptor.

Locally, SMTP points at Mailpit (see docker-compose.yml), so links containing tokens
are never written to logs.

- `send` never raises: used for security emails (invitations, password resets) sent as a
  background task after the response.
- `deliver` raises a DeliveryError: used by the notification worker, which retries
  transient failures.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings
from app.integrations.delivery import PermanentDeliveryError, TransientDeliveryError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...

    def deliver(self, message: OutgoingEmail) -> None: ...


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: OutgoingEmail) -> None:
        try:
            self.deliver(message)
        except (TransientDeliveryError, PermanentDeliveryError):
            return

    def deliver(self, message: OutgoingEmail) -> None:
        s = self.settings
        mime = MimeMessage()
        mime["From"] = s.email_from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
                if s.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if s.smtp_username and s.smtp_password:
                    smtp.login(s.smtp_username, s.smtp_password)
                smtp.send_message(mime)
        except smtplib.SMTPRecipientsRefused as exc:
            logger.error("email_send_failed", extra={"error": "recipient_refused"})
            raise PermanentDeliveryError("The mail server refused the recipient.") from exc
        except (OSError, smtplib.SMTPException) as exc:
            # Never log message bodies: they can contain single-use tokens.
            logger.error(
                "email_send_failed", extra={"subject": message.subject, "error": type(exc).__name__}
            )
            raise TransientDeliveryError(f"Mail server error: {type(exc).__name__}") from exc
        logger.info("email_sent", extra={"subject": message.subject})


class LogEmailSender:
    """EMAIL_PROVIDER=log: records that an email would have been sent, without sending.
    Logs only the recipient's domain and the subject; bodies can hold single-use links."""

    def send(self, message: OutgoingEmail) -> None:
        self.deliver(message)

    def deliver(self, message: OutgoingEmail) -> None:
        logger.info(
            "email_logged_not_sent",
            extra={"to_domain": message.to.rpartition("@")[2], "subject": message.subject},
        )


class InMemoryEmailSender:
    """Used in tests. Set `fail_with` to make the next deliveries raise."""

    def __init__(self) -> None:
        self.outbox: list[OutgoingEmail] = []
        self.fail_with: Exception | None = None

    def send(self, message: OutgoingEmail) -> None:
        self.outbox.append(message)

    def deliver(self, message: OutgoingEmail) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.outbox.append(message)


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_settings()
    if settings.email_provider == "log":
        return LogEmailSender()
    return SmtpEmailSender(settings)
