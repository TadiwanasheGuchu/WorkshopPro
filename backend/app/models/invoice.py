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
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(14, 2)


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Drafts have no number and can change. Issuing allocates the number and makes the
    invoice immutable (enforced by a database trigger); corrections use credit notes.

    amount_paid / amount_credited are maintained transactionally from allocations and
    credit notes, under a row lock, so balances never drift.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organisation_id", "invoice_number"),
        CheckConstraint("status IN ('draft', 'issued')", name="status_valid"),
        CheckConstraint(
            "status = 'draft' OR (invoice_number IS NOT NULL AND issue_date IS NOT NULL)",
            name="issued_has_number",
        ),
        CheckConstraint("amount_paid >= 0", name="paid_non_negative"),
        CheckConstraint("amount_credited >= 0 AND amount_credited <= total", name="credited_range"),
        Index("ix_invoices_org_status", "organisation_id", "status", "issue_date"),
        Index("ix_invoices_customer", "customer_id"),
        Index("ix_invoices_job", "job_card_id"),
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
    job_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT")
    )
    quotation_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_versions.id", ondelete="RESTRICT")
    )
    invoice_number: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(10), server_default="draft")
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency_code: Mapped[str] = mapped_column(String(3))
    prices_include_tax: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    amount_paid: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    amount_credited: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class InvoiceItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint("kind IN ('labour', 'part', 'fee', 'discount')", name="kind_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        Index("ix_invoice_items_invoice", "invoice_id", "position"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT")
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
    tax_rate_name: Mapped[str | None] = mapped_column(String(100))
    tax_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")
    line_subtotal: Mapped[Decimal] = mapped_column(MONEY)
    line_tax: Mapped[Decimal] = mapped_column(MONEY)
    line_total: Mapped[Decimal] = mapped_column(MONEY)


class CreditNote(UUIDPrimaryKeyMixin, Base):
    """Reduces what is owed on an issued invoice. Immutable once created."""

    __tablename__ = "credit_notes"
    __table_args__ = (
        UniqueConstraint("organisation_id", "credit_note_number"),
        CheckConstraint("total > 0", name="total_positive"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), index=True
    )
    credit_note_number: Mapped[str] = mapped_column(String(30))
    issue_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(500))
    currency_code: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(MONEY)
    tax_total: Mapped[Decimal] = mapped_column(MONEY)
    total: Mapped[Decimal] = mapped_column(MONEY)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class CreditNoteItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "credit_note_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    credit_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_notes.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_price: Mapped[Decimal] = mapped_column(MONEY)
    tax_rate_name: Mapped[str | None] = mapped_column(String(100))
    tax_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    line_subtotal: Mapped[Decimal] = mapped_column(MONEY)
    line_tax: Mapped[Decimal] = mapped_column(MONEY)
    line_total: Mapped[Decimal] = mapped_column(MONEY)


class Payment(UUIDPrimaryKeyMixin, Base):
    """Money received (payment) or paid back (refund), or a reversal of a mistaken
    payment. Never edited or deleted. `amount` is always positive; direction comes
    from `kind`."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("organisation_id", "receipt_number"),
        UniqueConstraint("organisation_id", "idempotency_key"),
        CheckConstraint("kind IN ('payment', 'refund', 'reversal')", name="kind_valid"),
        CheckConstraint(
            "method IN ('cash', 'eft', 'card', 'mobile', 'cheque', 'other')", name="method_valid"
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "kind <> 'reversal' OR reverses_payment_id IS NOT NULL", name="reversal_has_target"
        ),
        Index("ix_payments_customer", "customer_id", "received_at"),
        Index("ix_payments_org_received", "organisation_id", "received_at"),
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
    kind: Mapped[str] = mapped_column(String(10), server_default="payment")
    receipt_number: Mapped[str] = mapped_column(String(30))
    method: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency_code: Mapped[str] = mapped_column(String(3))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(String(1000))
    reverses_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), unique=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PaymentAllocation(UUIDPrimaryKeyMixin, Base):
    """How much of a payment settles which invoice. Negative for refunds/reversals."""

    __tablename__ = "payment_allocations"
    __table_args__ = (CheckConstraint("amount <> 0", name="amount_non_zero"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(MONEY)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
