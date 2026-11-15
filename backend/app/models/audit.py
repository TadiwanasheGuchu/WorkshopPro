import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail. A database trigger rejects UPDATE and DELETE.

    `changes` holds `{"field": [old, new]}` for updates, or a snapshot/context for
    other actions. Never store passwords, tokens or unnecessary personal data here.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organisation_id", text("created_at DESC")),
        Index("ix_audit_logs_entity", "organisation_id", "entity_type", "entity_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    actor_type: Mapped[str] = mapped_column(String(20))  # user | system | cli
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(String(300))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
