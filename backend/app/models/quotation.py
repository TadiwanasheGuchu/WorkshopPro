import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(14, 2)


class Quotation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A quotation for a job card. Its content lives in numbered versions."""

    __tablename__ = "quotations"
    __table_args__ = (
        UniqueConstraint("organisation_id", "quote_number"),
        # One quotation per job; further work becomes a new version needing new approval.
        UniqueConstraint("job_card_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    job_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    quote_number: Mapped[str] = mapped_column(String(30))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class QuotationVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One immutable-once-sent version. Approval always refers to a specific version."""

    __tablename__ = "quotation_versions"
    __table_args__ = (
        UniqueConstraint("quotation_id", "version_number"),
        CheckConstraint(
            "status IN ('draft', 'sent', 'approved', 'rejected', 'superseded', 'withdrawn')",
            name="status_valid",
        ),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_valid"),
        # Only one version of a quotation is the live one (not superseded/withdrawn).
        Index(
            "uq_quotation_versions_one_current",
            "quotation_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'sent', 'approved', 'rejected')"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="RESTRICT"), index=True
    )
    version_number: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(12), server_default="draft")
    currency_code: Mapped[str] = mapped_column(String(3))
    prices_include_tax: Mapped[bool] = mapped_column(Boolean)
    valid_until: Mapped[date | None] = mapped_column(Date)
    terms: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    revision_reason: Mapped[str | None] = mapped_column(String(500))


class QuotationItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quotation_items"
    __table_args__ = (
        CheckConstraint("kind IN ('labour', 'part', 'fee', 'discount')", name="kind_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        Index("ix_quotation_items_version", "version_id", "position"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_versions.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(500))
    part_number: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_price: Mapped[Decimal] = mapped_column(MONEY)
    tax_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_rates.id", ondelete="RESTRICT")
    )
    # Snapshot of the rate when the line was saved, so later rate edits never change it.
    tax_rate_name: Mapped[str | None] = mapped_column(String(100))
    tax_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")
    line_subtotal: Mapped[Decimal] = mapped_column(MONEY)
    line_tax: Mapped[Decimal] = mapped_column(MONEY)
    line_total: Mapped[Decimal] = mapped_column(MONEY)


class QuotationDecision(UUIDPrimaryKeyMixin, Base):
    """The customer's approval or rejection of one exact version and total."""

    __tablename__ = "quotation_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'rejected')", name="decision_valid"),
        CheckConstraint(
            "method IN ('customer_link', 'customer_portal', 'in_person', 'phone', 'email', "
            "'whatsapp', 'other')",
            name="method_valid",
        ),
        CheckConstraint(
            "method IN ('customer_link', 'customer_portal') OR recorded_by_user_id IS NOT NULL",
            name="staff_recorded_has_actor",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_versions.id", ondelete="RESTRICT"), unique=True
    )
    decision: Mapped[str] = mapped_column(String(10))
    method: Mapped[str] = mapped_column(String(15))
    # Exact total the customer agreed to, duplicated from the version as evidence.
    total: Mapped[Decimal] = mapped_column(MONEY)
    currency_code: Mapped[str] = mapped_column(String(3))
    customer_name: Mapped[str] = mapped_column(String(200))
    evidence: Mapped[str | None] = mapped_column(String(1000))
    comments: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class QuotationLink(UUIDPrimaryKeyMixin, Base):
    """A public link for the customer to view one version and decide once.

    Random 256-bit token (hash stored), expiring, single-purpose and single-use.
    Opening the link records `last_viewed_at`; it never counts as approval.
    """

    __tablename__ = "quotation_links"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_versions.id", ondelete="RESTRICT"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    view_count: Mapped[int] = mapped_column(Integer, server_default="0")
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
