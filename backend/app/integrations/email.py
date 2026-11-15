"""Email delivery adaptor.

Locally, SMTP points at Mailpit (see docker-compose.yml), so links containing tokens
are never written to logs. Delivery currently runs as a FastAPI background task after
the response; it moves to Celery with retries in Phase 5 (notifications).
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: OutgoingEmail) -> None:
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
        except (OSError, smtplib.SMTPException) as exc:
            # Never log message bodies: they can contain single-use tokens.
            logger.error(
                "email_send_failed", extra={"subject": message.subject, "error": type(exc).__name__}
            )
            return
        logger.info("email_sent", extra={"subject": message.subject})


class InMemoryEmailSender:
    """Used in tests."""

    def __init__(self) -> None:
        self.outbox: list[OutgoingEmail] = []

    def send(self, message: OutgoingEmail) -> None:
        self.outbox.append(message)


@lru_cache
def get_email_sender() -> EmailSender:
    return SmtpEmailSender(get_settings())
