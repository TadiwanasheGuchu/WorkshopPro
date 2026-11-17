import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import OptionalStr, Schema
from app.schemas.job_card import Ref

Event = Literal[
    "vehicle_received",
    "quotation_sent",
    "ready_for_collection",
    "invoice_issued",
    "appointment_confirmed",
    "service_reminder",
]
Status = Literal["queued", "sent", "delivered", "read", "failed", "skipped"]
Channel = Literal["email", "whatsapp", "none"]


class TemplateUpdate(Schema):
    is_enabled: bool
    email_subject: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    email_body: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    whatsapp_template_name: OptionalStr = Field(
        None,
        max_length=100,
        pattern=r"^[a-z0-9_]+$",
        description="Name of the template approved by Meta for this event. Empty disables "
        "WhatsApp for the event.",
    )
    whatsapp_language: Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(_[A-Z]{2})?$")] = "en"


class TemplateRead(BaseModel):
    event: Event
    label: str
    is_enabled: bool
    email_subject: str
    email_body: str
    whatsapp_template_name: str | None
    whatsapp_language: str
    whatsapp_params: list[str] = Field(
        description="Placeholders sent as the WhatsApp template's body parameters, in order."
    )
    placeholders: dict[str, str]


class NotificationRead(BaseModel):
    id: uuid.UUID
    event: Event
    event_label: str
    channel: Channel
    recipient: str | None
    subject: str | None
    body: str
    status: Status
    skip_reason: str | None
    attempts: int
    last_error: str | None
    provider: str | None
    customer: Ref
    related_type: str | None
    related_id: uuid.UUID | None
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    failed_at: datetime | None
    can_retry: bool
