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
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An individual or company that brings vehicles to the workshop.

    Customers belong to the organisation (not a branch): any branch can serve them.
    """

    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("customer_type IN ('individual', 'company')", name="customer_type_valid"),
        CheckConstraint(
            "(customer_type = 'individual' AND last_name IS NOT NULL) "
            "OR (customer_type = 'company' AND company_name IS NOT NULL)",
            name="name_present",
        ),
        CheckConstraint(
            "preferred_contact_method IN ('phone', 'whatsapp', 'email', 'sms')",
            name="preferred_contact_valid",
        ),
        Index(
            "ix_customers_display_name_trgm",
            "display_name",
            postgresql_using="gin",
            postgresql_ops={"display_name": "gin_trgm_ops"},
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    customer_type: Mapped[str] = mapped_column(String(20))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    company_name: Mapped[str | None] = mapped_column(String(200))
    contact_person: Mapped[str | None] = mapped_column(String(200))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    tax_number: Mapped[str | None] = mapped_column(String(100))
    # Denormalised for sorting and fuzzy search; maintained by the service layer.
    display_name: Mapped[str] = mapped_column(String(300))
    preferred_contact_method: Mapped[str] = mapped_column(String(20), server_default="phone")
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CustomerContact(UUIDPrimaryKeyMixin, Base):
    """A phone number or email address. One primary per kind per customer."""

    __tablename__ = "customer_contacts"
    __table_args__ = (
        CheckConstraint("kind IN ('phone', 'email')", name="kind_valid"),
        Index(
            "uq_customer_contacts_one_primary",
            "customer_id",
            "kind",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index("ix_customer_contacts_org_value", "organisation_id", "value"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    label: Mapped[str | None] = mapped_column(String(50))
    # Phones are stored digits-only with optional leading +; emails lowercased.
    value: Mapped[str] = mapped_column(CITEXT)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    position: Mapped[int] = mapped_column(SmallInteger, server_default="0")


class CustomerAddress(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "customer_addresses"
    __table_args__ = (CheckConstraint("kind IN ('physical', 'postal')", name="kind_valid"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(SmallInteger, server_default="0")


class CustomerConsent(UUIDPrimaryKeyMixin, Base):
    """Append-only record of communication consent. The latest record per channel is
    the current state; earlier records remain as evidence."""

    __tablename__ = "customer_consents"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('whatsapp', 'sms', 'email', 'marketing')", name="channel_valid"
        ),
        CheckConstraint("status IN ('granted', 'withdrawn')", name="status_valid"),
        CheckConstraint(
            "method IN ('verbal', 'written', 'signed_form', 'customer_portal', 'other')",
            name="method_valid",
        ),
        Index("ix_customer_consents_lookup", "customer_id", "channel", text("recorded_at DESC")),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10))
    method: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[str | None] = mapped_column(String(500))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        # A registration or VIN identifies one active vehicle per organisation. Archived
        # vehicles keep their history without blocking re-registration.
        Index(
            "uq_vehicles_registration_active",
            "organisation_id",
            "registration_key",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND registration_key IS NOT NULL"),
        ),
        Index(
            "uq_vehicles_vin_active",
            "organisation_id",
            "vin",
            unique=True,
            postgresql_where=text("archived_at IS NULL AND vin IS NOT NULL"),
        ),
        CheckConstraint(
            "registration_key IS NOT NULL OR vin IS NOT NULL", name="identifier_present"
        ),
        CheckConstraint("year IS NULL OR (year BETWEEN 1900 AND 2100)", name="year_range"),
        CheckConstraint("odometer_km IS NULL OR odometer_km >= 0", name="odometer_positive"),
        CheckConstraint(
            "fuel_type IS NULL OR fuel_type IN "
            "('petrol', 'diesel', 'hybrid', 'electric', 'lpg', 'other')",
            name="fuel_type_valid",
        ),
        CheckConstraint(
            "transmission IS NULL OR transmission IN ('manual', 'automatic', 'other')",
            name="transmission_valid",
        ),
        Index("ix_vehicles_org_customer", "organisation_id", "customer_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT")
    )
    # As written on the plate (uppercased), e.g. "N 12345 W".
    registration_number: Mapped[str | None] = mapped_column(String(20))
    # Letters and digits only, for matching "N12345W" against "N 12345 W".
    registration_key: Mapped[str | None] = mapped_column(String(20))
    vin: Mapped[str | None] = mapped_column(String(17))
    engine_number: Mapped[str | None] = mapped_column(String(50))
    make: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    variant: Mapped[str | None] = mapped_column(String(100))
    year: Mapped[int | None] = mapped_column(SmallInteger)
    fuel_type: Mapped[str | None] = mapped_column(String(20))
    transmission: Mapped[str | None] = mapped_column(String(20))
    colour: Mapped[str | None] = mapped_column(String(40))
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    odometer_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    existing_damage: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VehicleOwnership(UUIDPrimaryKeyMixin, Base):
    """Ownership history. The open record (ended_at IS NULL) matches vehicles.customer_id."""

    __tablename__ = "vehicle_ownerships"
    __table_args__ = (
        Index(
            "uq_vehicle_ownerships_one_current",
            "vehicle_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT")
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(300))
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
