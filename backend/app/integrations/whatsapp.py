"""WhatsApp delivery through the official WhatsApp Business Platform (CLAUDE.md §3.10).

Business-initiated messages must use templates approved by Meta; the template name,
language and ordered body parameters are configured per notification event. Personal
WhatsApp Web automation is never used. Credentials come from the environment and are
never sent to the browser.
"""

import logging
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.integrations.delivery import PermanentDeliveryError, TransientDeliveryError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhatsAppTemplateMessage:
    to: str  # E.164 without "+", e.g. 264811234567
    template_name: str
    language: str
    params: list[str] = field(default_factory=list)


class WhatsAppSender(Protocol):
    name: str

    def send(self, message: WhatsAppTemplateMessage) -> str:
        """Send and return the provider's message id."""
        ...


class LogWhatsAppSender:
    """Records the message without sending. The default until a provider is configured."""

    name = "log"

    def __init__(self) -> None:
        self.sent: list[WhatsAppTemplateMessage] = []
        self.fail_with: Exception | None = None

    def send(self, message: WhatsAppTemplateMessage) -> str:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(message)
        logger.info("whatsapp_logged", extra={"template": message.template_name})
        return f"log-{uuid.uuid4().hex}"


class MetaCloudWhatsAppSender:
    name = "meta"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=15)

    def send(self, message: WhatsAppTemplateMessage) -> str:
        s = self.settings
        if not (s.whatsapp_phone_number_id and s.whatsapp_access_token):
            raise PermanentDeliveryError("WhatsApp is not configured.")
        payload = {
            "messaging_product": "whatsapp",
            "to": message.to,
            "type": "template",
            "template": {
                "name": message.template_name,
                "language": {"code": message.language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in message.params],
                    }
                ]
                if message.params
                else [],
            },
        }
        try:
            res = self.client.post(
                f"{s.whatsapp_api_base}/{s.whatsapp_phone_number_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {s.whatsapp_access_token}"},
            )
        except httpx.HTTPError as exc:
            raise TransientDeliveryError(f"WhatsApp request failed: {type(exc).__name__}") from exc
        if res.status_code == 429 or res.status_code >= 500:
            raise TransientDeliveryError(f"WhatsApp provider returned {res.status_code}.")
        if res.status_code >= 400:
            try:
                detail = res.json().get("error", {}).get("message", "")
            except ValueError:
                detail = ""
            raise PermanentDeliveryError(
                f"WhatsApp rejected the message ({res.status_code}): {detail}"[:300]
            )
        try:
            return str(res.json()["messages"][0]["id"])
        except (ValueError, KeyError, IndexError) as exc:
            raise TransientDeliveryError("Unexpected response from WhatsApp.") from exc


@lru_cache
def get_whatsapp_sender() -> WhatsAppSender:
    settings = get_settings()
    if settings.whatsapp_provider == "meta":
        return MetaCloudWhatsAppSender(settings)
    return LogWhatsAppSender()
