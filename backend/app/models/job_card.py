import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

JOB_STATUSES = (
    "vehicle_received",
    "inspection_pending",
    "diagnosis_in_progress",
    "awaiting_approval",
    "awaiting_parts",
    "repair_in_progress",
    "quality_inspection",
    "ready_for_collection",
    "completed",
    "cancelled",
)
_STATUS_LIST = ", ".join(f"'{s}'" for s in JOB_STATUSES)


class JobCard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The central operational record for one visit of one vehicle."""

    __tablename__ = "job_cards"
    __table_args__ = (
        UniqueConstraint("organisation_id", "job_number"),
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="status_valid"),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="priority_valid"),
        CheckConstraint(
            "fuel_level IS NULL OR fuel_level IN "
            "('empty', 'quarter', 'half', 'three_quarters', 'full')",
            name="fuel_level_valid",
        ),
        CheckConstraint(
            "intake_odometer_km IS NULL OR intake_odometer_km >= 0", name="odometer_positive"
        ),
        CheckConstraint(
            "status <> 'completed' OR collected_at IS NOT NULL", name="completed_has_collection"
        ),
        CheckConstraint(
            "status <> 'cancelled' OR cancellation_reason IS NOT NULL", name="cancelled_has_reason"
        ),
        Index("ix_job_cards_branch_status", "organisation_id", "branch_id", "status"),
        Index("ix_job_cards_vehicle", "vehicle_id", text("received_at DESC")),
        Index("ix_job_cards_customer", "customer_id"),
        Index("ix_job_cards_received", "organisation_id", text("received_at DESC")),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    job_number: Mapped[str] = mapped_column(String(30))
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT")
    )
    service_bay_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_bays.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30), server_default="vehicle_received")
    priority: Mapped[str] = mapped_column(String(10), server_default="normal")
    complaint: Mapped[str] = mapped_column(Text)
    requested_work: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    work_performed: Mapped[str | None] = mapped_column(Text)
    intake_odometer_km: Mapped[int | None] = mapped_column(Integer)
    fuel_level: Mapped[str | None] = mapped_column(String(20))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    promised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_by_name: Mapped[str | None] = mapped_column(String(200))
    handover_notes: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    # Optimistic concurrency: clients send the version they saw; stale edits get 409.
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class JobStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "job_status_history"
    __table_args__ = (Index("ix_job_status_history_job", "job_card_id", "changed_at"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT")
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(1000))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class JobAssignment(UUIDPrimaryKeyMixin, Base):
    """A mechanic assigned to a job. Unassigning closes the row; history is kept."""

    __tablename__ = "job_assignments"
    __table_args__ = (
        Index(
            "uq_job_assignments_active",
            "job_card_id",
            "user_id",
            unique=True,
            postgresql_where=text("unassigned_at IS NULL"),
        ),
        Index(
            "ix_job_assignments_user_active",
            "user_id",
            postgresql_where=text("unassigned_at IS NULL"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unassigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class JobNote(UUIDPrimaryKeyMixin, Base):
    """Append-only work notes. 'customer' notes may later be shown in the portal."""

    __tablename__ = "job_notes"
    __table_args__ = (
        CheckConstraint("visibility IN ('internal', 'customer')", name="visibility_valid"),
        Index("ix_job_notes_job", "job_card_id", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT")
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    visibility: Mapped[str] = mapped_column(String(10), server_default="internal")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class JobApprovalException(UUIDPrimaryKeyMixin, Base):
    """A documented, authorised exception allowing chargeable work to start without an
    approved quotation (CLAUDE.md §3.4). Revocable; never deleted."""

    __tablename__ = "job_approval_exceptions"
    __table_args__ = (
        CheckConstraint(
            "exception_type IN ('customer_verbal', 'customer_written', 'warranty', "
            "'internal_no_charge', 'safety_emergency', 'other')",
            name="exception_type_valid",
        ),
        CheckConstraint("max_amount IS NULL OR max_amount >= 0", name="max_amount_positive"),
        CheckConstraint(
            "revoked_at IS NULL OR revoke_reason IS NOT NULL", name="revoked_has_reason"
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT"), index=True
    )
    exception_type: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(1000))
    scope: Mapped[str] = mapped_column(String(1000))
    customer_contact: Mapped[str | None] = mapped_column(String(200))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str] = mapped_column(String(3), server_default="NAD")
    authorised_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    authorised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(500))
