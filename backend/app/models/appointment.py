import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A booked workshop slot. Checking in converts it into a job card."""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        CheckConstraint(
            "status IN ('booked', 'arrived', 'cancelled', 'no_show')", name="status_valid"
        ),
        CheckConstraint(
            "status <> 'cancelled' OR cancellation_reason IS NOT NULL", name="cancelled_has_reason"
        ),
        CheckConstraint("status <> 'arrived' OR job_card_id IS NOT NULL", name="arrived_has_job"),
        Index("ix_appointments_branch_start", "organisation_id", "branch_id", "starts_at"),
        Index("ix_appointments_bay_start", "service_bay_id", "starts_at"),
        Index("ix_appointments_mechanic_start", "assigned_user_id", "starts_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT")
    )
    service_bay_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_bays.id", ondelete="RESTRICT")
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), server_default="booked")
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    job_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT"), unique=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class AppointmentRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A customer's request for a booking (from the portal). Staff confirm it into an
    Appointment, or decline it with a reason."""

    __tablename__ = "appointment_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'declined', 'cancelled')", name="status_valid"
        ),
        CheckConstraint("time_of_day IN ('morning', 'afternoon', 'any')", name="time_of_day_valid"),
        CheckConstraint(
            "status <> 'confirmed' OR appointment_id IS NOT NULL", name="confirmed_has_booking"
        ),
        Index("ix_appointment_requests_branch_status", "branch_id", "status", "preferred_date"),
        Index("ix_appointment_requests_customer", "customer_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT")
    )
    preferred_date: Mapped[date] = mapped_column(Date)
    time_of_day: Mapped[str] = mapped_column(String(10))
    service_requested: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), server_default="pending")
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="RESTRICT")
    )
    decline_reason: Mapped[str | None] = mapped_column(String(500))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
