"""Customer notifications (CLAUDE.md §3.10): per-event templates and a delivery log.

The log never stores single-use links (quotation approval tokens); the link travels only
with the background job that sends the message.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

EVENTS = ("vehicle_received", "quotation_sent", "ready_for_collection", "invoice_issued")
STATUSES = ("queued", "sent", "delivered", "read", "failed", "skipped")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class NotificationTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Organisation overrides. Events without a row use the built-in defaults."""

    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint("organisation_id", "event"),
        CheckConstraint(f"event IN {_in(EVENTS)}", name="event_valid"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    event: Mapped[str] = mapped_column(String(40))
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    email_subject: Mapped[str] = mapped_column(String(200))
    email_body: Mapped[str] = mapped_column(Text)
    # WhatsApp business-initiated messages must use a template approved by Meta.
    whatsapp_template_name: Mapped[str | None] = mapped_column(String(100))
    whatsapp_language: Mapped[str] = mapped_column(String(10), server_default="en")


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"event IN {_in(EVENTS)}", name="event_valid"),
        CheckConstraint(f"status IN {_in(STATUSES)}", name="status_valid"),
        CheckConstraint("channel IN ('email', 'whatsapp', 'none')", name="channel_valid"),
        Index("ix_notifications_org_created", "organisation_id", "created_at"),
        Index("ix_notifications_customer", "customer_id", "created_at"),
        Index("ix_notifications_provider_id", "provider_message_id"),
        Index(
            "ix_notifications_queued",
            "created_at",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    event: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(10))
    recipient: Mapped[str | None] = mapped_column(String(254))
    subject: Mapped[str | None] = mapped_column(String(200))
    # Rendered text; single-use links are replaced by a placeholder.
    body: Mapped[str] = mapped_column(Text)
    # Ordered WhatsApp template parameters (links redacted), as sent.
    template_params: Mapped[str | None] = mapped_column(Text)
    has_secret_link: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(10), server_default="queued")
    skip_reason: Mapped[str | None] = mapped_column(String(300))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500))
    provider: Mapped[str | None] = mapped_column(String(20))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    related_type: Mapped[str | None] = mapped_column(String(30))
    related_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
