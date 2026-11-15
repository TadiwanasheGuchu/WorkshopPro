import uuid
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Branch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code"),
        CheckConstraint("code ~ '^[A-Z0-9-]{1,12}$'", name="code_format"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(12))
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None] = mapped_column(String(50))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BranchOperatingHours(Base):
    __tablename__ = "branch_operating_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint(
            "is_closed OR (opens_at IS NOT NULL AND closes_at IS NOT NULL "
            "AND opens_at < closes_at)",
            name="hours_valid",
        ),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True
    )
    # ISO weekday index starting Monday = 0.
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    is_closed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    opens_at: Mapped[time | None] = mapped_column(Time)
    closes_at: Mapped[time | None] = mapped_column(Time)


class ServiceBay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_bays"
    __table_args__ = (UniqueConstraint("branch_id", "name"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
