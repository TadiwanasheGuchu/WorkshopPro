"""Parts catalogue, stock locations and the stock movement ledger (CLAUDE.md §3.7).

The ledger (`stock_movements`) is the source of truth. `stock_levels.on_hand` is a running
balance maintained by a database trigger on every movement insert, so it cannot drift
from the ledger. Movements are append-only; corrections are new movements.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
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

MOVEMENT_KINDS = (
    "opening",  # first count when stock is loaded
    "adjustment",  # stocktake correction, damage, loss (signed)
    "transfer_out",
    "transfer_in",
    "receipt",  # goods received from a supplier
    "issue",  # fitted to / used on a job (negative)
    "return",  # returned from a job (positive)
    "supplier_return",  # sent back to the supplier (negative)
)


class PartCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "part_categories"
    __table_args__ = (UniqueConstraint("organisation_id", "name"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(CITEXT)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Part(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "parts"
    __table_args__ = (
        UniqueConstraint("organisation_id", "sku"),
        CheckConstraint("cost_price >= 0", name="cost_non_negative"),
        CheckConstraint("selling_price >= 0", name="price_non_negative"),
        Index(
            "ix_parts_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    sku: Mapped[str] = mapped_column(CITEXT)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("part_categories.id", ondelete="RESTRICT"), index=True
    )
    unit: Mapped[str] = mapped_column(String(20), server_default="each")
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    manufacturer_part_number: Mapped[str | None] = mapped_column(String(100))
    cost_price: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    selling_price: Mapped[Decimal] = mapped_column(MONEY, server_default="0")
    tax_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_rates.id", ondelete="RESTRICT")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A store room, shelf area or van belonging to a branch."""

    __tablename__ = "stock_locations"
    __table_args__ = (
        UniqueConstraint("branch_id", "name"),
        Index(
            "uq_stock_locations_default_per_branch",
            "branch_id",
            unique=True,
            postgresql_where=text("is_default AND archived_at IS NULL"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    is_default: Mapped[bool] = mapped_column(server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockLevel(Base):
    """Running balance per part and location. on_hand is written only by the movement
    trigger; reserved is maintained by reservations under a row lock."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="reserved_non_negative"),
        CheckConstraint("reserved <= on_hand", name="reserved_within_on_hand"),
        CheckConstraint("min_quantity IS NULL OR min_quantity >= 0", name="min_non_negative"),
        Index("ix_stock_levels_part", "part_id"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id", ondelete="RESTRICT"), primary_key=True
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT"), primary_key=True
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    on_hand: Mapped[Decimal] = mapped_column(QTY, server_default="0")
    reserved: Mapped[Decimal] = mapped_column(QTY, server_default="0")
    min_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StockOperation(UUIDPrimaryKeyMixin, Base):
    """One user action that changes stock (an adjustment, a transfer, an issue...). Groups
    its movements and carries the idempotency key so a retried request applies once."""

    __tablename__ = "stock_operations"
    __table_args__ = (
        UniqueConstraint("organisation_id", "idempotency_key"),
        Index("ix_stock_operations_org_created", "organisation_id", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(100))
    job_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StockMovement(UUIDPrimaryKeyMixin, Base):
    """Append-only ledger line. quantity is signed: positive adds stock."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="quantity_non_zero"),
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in MOVEMENT_KINDS) + ")", name="kind_valid"
        ),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        Index("ix_stock_movements_part_location", "part_id", "location_id", "created_at"),
        Index("ix_stock_movements_org_created", "organisation_id", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT")
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_operations.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id", ondelete="RESTRICT")
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
    balance_after: Mapped[Decimal | None] = mapped_column(QTY)
    job_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_cards.id", ondelete="RESTRICT"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StockReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stock held for an authorised job at a location. Outstanding = quantity - issued -
    released. stock_levels.reserved equals the outstanding total of open reservations for
    the same part and location (maintained under the stock-level row lock)."""

    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("issued_quantity >= 0", name="issued_non_negative"),
        CheckConstraint("released_quantity >= 0", name="released_non_negative"),
        CheckConstraint("issued_quantity + released_quantity <= quantity", name="within_quantity"),
        CheckConstraint("status IN ('open', 'closed')", name="status_valid"),
        Index("ix_stock_reservations_job", "job_card_id"),
        Index(
            "ix_stock_reservations_open",
            "location_id",
            "part_id",
            postgresql_where=text("status = 'open'"),
        ),
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
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_locations.id", ondelete="RESTRICT")
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id", ondelete="RESTRICT")
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_operations.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(QTY)
    issued_quantity: Mapped[Decimal] = mapped_column(QTY, server_default="0")
    released_quantity: Mapped[Decimal] = mapped_column(QTY, server_default="0")
    status: Mapped[str] = mapped_column(String(10), server_default="open")
    release_reason: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
