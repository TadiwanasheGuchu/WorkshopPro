import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Organisation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    tax_number: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone: Mapped[str | None] = mapped_column(String(50))
    website: Mapped[str | None] = mapped_column(String(200))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country_code: Mapped[str] = mapped_column(String(2), server_default="NA")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class OrganisationSettings(TimestampMixin, Base):
    __tablename__ = "organisation_settings"
    __table_args__ = (
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_iso"),
        CheckConstraint(
            "date_format IN ('DD/MM/YYYY', 'YYYY-MM-DD', 'MM/DD/YYYY')", name="date_format_valid"
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), primary_key=True
    )
    currency_code: Mapped[str] = mapped_column(String(3), server_default="NAD")
    timezone: Mapped[str] = mapped_column(String(64), server_default="Africa/Windhoek")
    date_format: Mapped[str] = mapped_column(String(10), server_default="DD/MM/YYYY")
    prices_include_tax: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    document_footer: Mapped[str | None] = mapped_column(Text)
    quotation_validity_days: Mapped[int] = mapped_column(Integer, server_default="14")
    quotation_terms: Mapped[str | None] = mapped_column(Text)
    invoice_payment_days: Mapped[int] = mapped_column(Integer, server_default="0")
    invoice_terms: Mapped[str | None] = mapped_column(Text)


class TaxRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configurable tax rates. No rate is seeded: rates must be confirmed with a
    qualified Namibian tax adviser and entered by the organisation."""

    __tablename__ = "tax_rates"
    __table_args__ = (
        CheckConstraint("rate_percent >= 0 AND rate_percent <= 100", name="rate_percent_range"),
        UniqueConstraint("organisation_id", "name"),
        # At most one active default rate per organisation.
        Index(
            "uq_tax_rates_one_default",
            "organisation_id",
            unique=True,
            postgresql_where=text("is_default AND is_active"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    description: Mapped[str | None] = mapped_column(String(300))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class DocumentSequence(TimestampMixin, Base):
    """Per-organisation numbering for job cards, quotations, invoices, etc.

    Numbers are allocated with SELECT ... FOR UPDATE inside the creating transaction
    (see app/services/numbering.py), so they are gap-free per committed transaction
    and never duplicated.
    """

    __tablename__ = "document_sequences"
    __table_args__ = (
        CheckConstraint("next_number >= 1", name="next_number_positive"),
        CheckConstraint("padding BETWEEN 1 AND 10", name="padding_range"),
        CheckConstraint("prefix ~ '^[A-Z0-9-]{0,10}$'", name="prefix_format"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), primary_key=True
    )
    document_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(10))
    next_number: Mapped[int] = mapped_column(Integer, server_default="1")
    padding: Mapped[int] = mapped_column(Integer, server_default="6")
    last_allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
