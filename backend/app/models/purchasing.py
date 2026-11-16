"""Suppliers, purchase orders, goods received notes and supplier returns
(CLAUDE.md §3.8). Stock arrives and leaves only through the stock movement ledger."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(14, 2)
QTY = Numeric(12, 2)

PO_STATUSES = ("draft", "approved", "partially_received", "received", "closed", "cancelled")


class Supplier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name"),
        CheckConstraint("payment_terms_days >= 0", name="terms_non_negative"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(CITEXT)
    contact_person: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(CITEXT)
    address: Mapped[str | None] = mapped_column(Text)
    tax_number: Mapped[str | None] = mapped_column(String(100))
    account_number: Mapped[str | None] = mapped_column(String(100))
    payment_terms_days: Mapped[int] = mapped_column(Integer, server_default="30")
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupplierPart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The supplier's code and last price for one of our parts."""

    __tablename__ = "supplier_parts"
    __table_args__ = (
        UniqueConstraint("supplier_id", "part_id"),
        CheckConstraint("last_cost IS NULL OR last_cost >= 0", name="cost_non_negative"),
        Index("ix_supplier_parts_part", "part_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT")
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT")
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(100))
    last_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    lead_time_days: Mapped[int | None] = mapped_column(SmallInteger)


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("organisation_id", "po_number"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in PO_STATUSES) + ")", name="status_valid"
        ),
        Index("ix_purchase_orders_org_status", "organisation_id", "status"),
        Index("ix_purchase_orders_supplier", "supplier_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT")
    )
    po_number: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), server_default="draft")
    currency_code: Mapped[str] = mapped_column(String(3))
    expected_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    total: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    closed_reason: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class PurchaseOrderLine(UUIDPrimaryKeyMixin, Base):
    """Amounts exclude tax. received/returned are maintained under the order's row lock."""

    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "part_id"),
        CheckConstraint("quantity_ordered > 0", name="ordered_positive"),
        CheckConstraint(
            "quantity_received >= 0 AND quantity_received <= quantity_ordered",
            name="received_range",
        ),
        CheckConstraint(
            "quantity_returned >= 0 AND quantity_returned <= quantity_received",
            name="returned_range",
        ),
        CheckConstraint("unit_cost >= 0", name="cost_non_negative"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT")
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(100))
    quantity_ordered: Mapped[Decimal] = mapped_column(QTY)
    quantity_received: Mapped[Decimal] = mapped_column(QTY, server_default="0")
    quantity_returned: Mapped[Decimal] = mapped_column(QTY, server_default="0")
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
    line_total: Mapped[Decimal] = mapped_column(MONEY)


class GoodsReceivedNote(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "goods_received_notes"
    __table_args__ = (
        UniqueConstraint("organisation_id", "grn_number"),
        Index("ix_grn_po", "purchase_order_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT")
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id", ondelete="RESTRICT")
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_operations.id", ondelete="RESTRICT")
    )
    grn_number: Mapped[str] = mapped_column(String(30))
    delivery_reference: Mapped[str | None] = mapped_column(String(100))
    supplier_invoice_reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    total: Mapped[Decimal] = mapped_column(MONEY)
    received_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class GoodsReceivedLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "goods_received_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    grn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_received_notes.id", ondelete="RESTRICT"), index=True
    )
    po_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order_lines.id", ondelete="RESTRICT")
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
    discrepancy: Mapped[str | None] = mapped_column(String(500))


class SupplierReturn(UUIDPrimaryKeyMixin, Base):
    """Stock sent back to the supplier against a purchase order (damaged, wrong part)."""

    __tablename__ = "supplier_returns"
    __table_args__ = (Index("ix_supplier_returns_po", "purchase_order_id"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT")
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id", ondelete="RESTRICT")
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_operations.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(100))
    total: Mapped[Decimal] = mapped_column(MONEY)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class SupplierReturnLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "supplier_return_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    supplier_return_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_returns.id", ondelete="RESTRICT"), index=True
    )
    po_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order_lines.id", ondelete="RESTRICT")
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
