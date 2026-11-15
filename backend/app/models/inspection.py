import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoredFile(UUIDPrimaryKeyMixin, Base):
    """Metadata for an object in storage. Bytes live in object storage, never in the DB."""

    __tablename__ = "stored_files"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(40))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class InspectionTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inspection_templates"
    __table_args__ = (
        Index(
            "uq_inspection_templates_name_active",
            "organisation_id",
            "name",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InspectionTemplateItem(UUIDPrimaryKeyMixin, Base):
    """A checklist line. Sections are a title on each item, ordered by position."""

    __tablename__ = "inspection_template_items"
    __table_args__ = (Index("ix_inspection_template_items_template", "template_id", "position"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_templates.id", ondelete="CASCADE")
    )
    section: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    guidance: Mapped[str | None] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(SmallInteger)


class Inspection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An inspection of a vehicle on a job card. Items are copied from the template when
    the inspection starts, so later template edits never change past inspections."""

    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("kind IN ('intake', 'quality', 'other')", name="kind_valid"),
        CheckConstraint("status IN ('draft', 'submitted')", name="status_valid"),
        CheckConstraint(
            "status = 'draft' OR (submitted_at IS NOT NULL AND submitted_by_user_id IS NOT NULL)",
            name="submitted_has_actor",
        ),
        Index("ix_inspections_job", "job_card_id", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT")
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_templates.id", ondelete="RESTRICT")
    )
    template_name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), server_default="draft")
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class InspectionItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inspection_items"
    __table_args__ = (
        CheckConstraint(
            "result IN ('pass', 'attention', 'fail', 'not_inspected')", name="result_valid"
        ),
        Index("ix_inspection_items_inspection", "inspection_id", "position"),
    )

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="RESTRICT")
    )
    section: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    guidance: Mapped[str | None] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(SmallInteger)
    result: Mapped[str] = mapped_column(String(15), server_default="not_inspected")
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class InspectionPhoto(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inspection_photos"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="RESTRICT"), index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_items.id", ondelete="RESTRICT"), index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="RESTRICT"), unique=True
    )
    caption: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class InspectionAmendment(UUIDPrimaryKeyMixin, Base):
    """A controlled change to a submitted inspection, with the reason and old values."""

    __tablename__ = "inspection_amendments"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="RESTRICT"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_items.id", ondelete="RESTRICT")
    )
    old_result: Mapped[str] = mapped_column(String(15))
    new_result: Mapped[str] = mapped_column(String(15))
    old_notes: Mapped[str | None] = mapped_column(Text)
    new_notes: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(500))
    amended_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    amended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
