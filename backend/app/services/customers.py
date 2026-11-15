"""Customers: profiles, contacts, addresses and communication consent.

Customers belong to the organisation; any branch with customer permissions can serve
them (Principal.require_in_any_branch).
"""

import re
import uuid
from typing import Any

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.time import utcnow
from app.models import (
    Customer,
    CustomerAddress,
    CustomerConsent,
    CustomerContact,
    User,
    Vehicle,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.customer import (
    AddressInput,
    AddressRead,
    ConsentInput,
    ConsentRead,
    ContactInput,
    ContactRead,
    CustomerCreate,
    CustomerDetail,
    CustomerSummary,
    CustomerUpdate,
    VehicleBrief,
    registration_key,
)
from app.services import audit
from app.services.common import get_scoped, paginate

_PROFILE_FIELDS = (
    "customer_type",
    "first_name",
    "last_name",
    "company_name",
    "contact_person",
    "registration_number",
    "tax_number",
    "preferred_contact_method",
    "notes",
)


def display_name_for(c: Customer) -> str:
    if c.customer_type == "company":
        return c.company_name or "Unnamed company"
    return " ".join(p for p in (c.first_name, c.last_name) if p) or "Unnamed customer"


def _replace_contacts(db: Session, customer: Customer, contacts: list[ContactInput]) -> None:
    db.execute(delete(CustomerContact).where(CustomerContact.customer_id == customer.id))
    seen_primary: set[str] = {c.kind for c in contacts if c.is_primary}
    for position, c in enumerate(contacts):
        # The first contact of each kind becomes primary if none was chosen.
        primary = c.is_primary or c.kind not in seen_primary
        if primary:
            seen_primary.add(c.kind)
        db.add(
            CustomerContact(
                organisation_id=customer.organisation_id,
                customer_id=customer.id,
                kind=c.kind,
                label=c.label,
                value=c.value,
                is_primary=primary,
                position=position,
            )
        )


def _replace_addresses(db: Session, customer: Customer, addresses: list[AddressInput]) -> None:
    db.execute(delete(CustomerAddress).where(CustomerAddress.customer_id == customer.id))
    for position, a in enumerate(addresses):
        db.add(
            CustomerAddress(
                organisation_id=customer.organisation_id,
                customer_id=customer.id,
                position=position,
                **a.model_dump(),
            )
        )


# --------------------------------------------------------------------------- reads


def _search_condition(organisation_id: uuid.UUID, search: str) -> Any:
    pattern = f"%{search}%"
    digits = re.sub(r"\D", "", search)
    reg = registration_key(search)
    contact_match = select(CustomerContact.id).where(
        CustomerContact.customer_id == Customer.id,
        or_(
            CustomerContact.value.ilike(pattern),
            *([CustomerContact.value.contains(digits)] if len(digits) >= 4 else []),
        ),
    )
    conditions = [
        Customer.display_name.ilike(pattern),
        Customer.contact_person.ilike(pattern),
        exists(contact_match),
    ]
    if len(reg) >= 2:
        conditions.append(
            exists(
                select(Vehicle.id).where(
                    Vehicle.customer_id == Customer.id,
                    Vehicle.organisation_id == organisation_id,
                    Vehicle.registration_key.contains(reg),
                )
            )
        )
    return or_(*conditions)


def _summaries(db: Session, customers: list[Customer]) -> list[CustomerSummary]:
    ids = [c.id for c in customers]
    primaries: dict[tuple[uuid.UUID, str], str] = {}
    vehicle_counts: dict[uuid.UUID, int] = {}
    if ids:
        for cid, kind, value in db.execute(
            select(CustomerContact.customer_id, CustomerContact.kind, CustomerContact.value).where(
                CustomerContact.customer_id.in_(ids), CustomerContact.is_primary
            )
        ):
            primaries[(cid, kind)] = value
        vehicle_counts = dict(
            db.execute(
                select(Vehicle.customer_id, func.count())
                .where(Vehicle.customer_id.in_(ids), Vehicle.archived_at.is_(None))
                .group_by(Vehicle.customer_id)
            ).all()
        )
    return [
        CustomerSummary(
            id=c.id,
            customer_type=c.customer_type,  # type: ignore[arg-type]
            display_name=c.display_name,
            primary_phone=primaries.get((c.id, "phone")),
            primary_email=primaries.get((c.id, "email")),
            vehicle_count=vehicle_counts.get(c.id, 0),
            archived_at=c.archived_at,
            created_at=c.created_at,
        )
        for c in customers
    ]


def list_customers(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    search: str | None = None,
    include_archived: bool = False,
) -> tuple[list[CustomerSummary], int]:
    principal.require_in_any_branch(P.CUSTOMERS_VIEW)
    stmt = select(Customer).where(Customer.organisation_id == principal.organisation_id)
    if not include_archived:
        stmt = stmt.where(Customer.archived_at.is_(None))
    if search:
        stmt = stmt.where(_search_condition(principal.organisation_id, search.strip()))
    items, total = paginate(db, stmt.order_by(Customer.display_name, Customer.id), params)
    return _summaries(db, items), total


def current_consents(db: Session, customer_id: uuid.UUID) -> list[ConsentRead]:
    rows = db.execute(
        select(CustomerConsent, User.full_name)
        .outerjoin(User, User.id == CustomerConsent.recorded_by_user_id)
        .where(CustomerConsent.customer_id == customer_id)
        .order_by(CustomerConsent.channel, CustomerConsent.recorded_at.desc())
        .ext(distinct_on(CustomerConsent.channel))
    ).all()
    return [_consent_read(c, name) for c, name in rows]


def _consent_read(c: CustomerConsent, recorded_by: str | None) -> ConsentRead:
    return ConsentRead(
        id=c.id,
        channel=c.channel,  # type: ignore[arg-type]
        status=c.status,  # type: ignore[arg-type]
        method=c.method,  # type: ignore[arg-type]
        evidence=c.evidence,
        recorded_at=c.recorded_at,
        recorded_by=recorded_by,
    )


def get_customer(db: Session, principal: Principal, customer_id: uuid.UUID) -> CustomerDetail:
    principal.require_in_any_branch(P.CUSTOMERS_VIEW)
    c = get_scoped(db, Customer, customer_id, principal.organisation_id)
    contacts = db.scalars(
        select(CustomerContact)
        .where(CustomerContact.customer_id == c.id)
        .order_by(CustomerContact.kind.desc(), CustomerContact.position)
    )
    addresses = db.scalars(
        select(CustomerAddress)
        .where(CustomerAddress.customer_id == c.id)
        .order_by(CustomerAddress.position)
    )
    vehicles = db.scalars(
        select(Vehicle)
        .where(Vehicle.customer_id == c.id)
        .order_by(Vehicle.archived_at.is_not(None), Vehicle.make, Vehicle.model)
    )
    return CustomerDetail(
        id=c.id,
        customer_type=c.customer_type,  # type: ignore[arg-type]
        display_name=c.display_name,
        first_name=c.first_name,
        last_name=c.last_name,
        company_name=c.company_name,
        contact_person=c.contact_person,
        registration_number=c.registration_number,
        tax_number=c.tax_number,
        preferred_contact_method=c.preferred_contact_method,  # type: ignore[arg-type]
        notes=c.notes,
        archived_at=c.archived_at,
        created_at=c.created_at,
        contacts=[ContactRead.model_validate(x) for x in contacts],
        addresses=[AddressRead.model_validate(x) for x in addresses],
        consents=current_consents(db, c.id),
        vehicles=[
            VehicleBrief(
                id=v.id,
                registration_number=v.registration_number,
                vin=v.vin,
                make=v.make,
                model=v.model,
                year=v.year,
                archived_at=v.archived_at,
            )
            for v in vehicles
        ],
    )


# --------------------------------------------------------------------------- writes


def create_customer(db: Session, principal: Principal, body: CustomerCreate) -> CustomerDetail:
    principal.require_in_any_branch(P.CUSTOMERS_MANAGE)
    customer = Customer(
        organisation_id=principal.organisation_id,
        **{f: getattr(body, f) for f in _PROFILE_FIELDS},
    )
    if customer.customer_type == "individual":
        customer.company_name = None
    customer.display_name = display_name_for(customer)
    db.add(customer)
    db.flush()
    _replace_contacts(db, customer, body.contacts)
    _replace_addresses(db, customer, body.addresses)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="customer.created",
        entity_type="customer",
        entity_id=customer.id,
        summary=f"Customer {customer.display_name} registered",
    )
    db.commit()
    return get_customer(db, principal, customer.id)


def update_customer(
    db: Session, principal: Principal, customer_id: uuid.UUID, body: CustomerUpdate
) -> CustomerDetail:
    principal.require_in_any_branch(P.CUSTOMERS_MANAGE)
    customer = get_scoped(db, Customer, customer_id, principal.organisation_id)
    data = body.changes()
    contacts = data.pop("contacts", None)
    addresses = data.pop("addresses", None)

    changes: dict[str, list[Any]] = {}
    for key, value in data.items():
        old = getattr(customer, key)
        if old != value:
            changes[key] = [old, value]
            setattr(customer, key, value)
    if customer.customer_type == "individual" and not customer.last_name:
        raise ConflictError("An individual customer needs a surname.")
    if customer.customer_type == "company" and not customer.company_name:
        raise ConflictError("A company customer needs a company name.")
    customer.display_name = display_name_for(customer)

    if contacts is not None:
        _replace_contacts(db, customer, body.contacts or [])
        changes["contacts"] = ["replaced", len(contacts)]
    if addresses is not None:
        _replace_addresses(db, customer, body.addresses or [])
        changes["addresses"] = ["replaced", len(addresses)]
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="customer.updated",
            entity_type="customer",
            entity_id=customer.id,
            summary=f"Customer {customer.display_name} updated",
            changes=changes,
        )
    db.commit()
    return get_customer(db, principal, customer.id)


def set_archived(
    db: Session, principal: Principal, customer_id: uuid.UUID, archived: bool
) -> CustomerDetail:
    principal.require_in_any_branch(P.CUSTOMERS_MANAGE)
    customer = get_scoped(db, Customer, customer_id, principal.organisation_id)
    if archived == (customer.archived_at is not None):
        return get_customer(db, principal, customer.id)
    if archived:
        active = db.scalar(
            select(func.count())
            .select_from(Vehicle)
            .where(Vehicle.customer_id == customer.id, Vehicle.archived_at.is_(None))
        )
        if active:
            raise ConflictError(
                "Transfer or archive this customer's vehicles before archiving the customer.",
                details={"active_vehicles": active},
            )
    customer.archived_at = utcnow() if archived else None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="customer.archived" if archived else "customer.restored",
        entity_type="customer",
        entity_id=customer.id,
        summary=f"Customer {customer.display_name} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return get_customer(db, principal, customer.id)


def record_consent(
    db: Session, principal: Principal, customer_id: uuid.UUID, body: ConsentInput
) -> ConsentRead:
    principal.require_in_any_branch(P.CUSTOMERS_MANAGE)
    customer = get_scoped(db, Customer, customer_id, principal.organisation_id)
    consent = CustomerConsent(
        organisation_id=principal.organisation_id,
        customer_id=customer.id,
        recorded_by_user_id=principal.user_id,
        **body.model_dump(),
    )
    db.add(consent)
    db.flush()
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="customer.consent_recorded",
        entity_type="customer",
        entity_id=customer.id,
        summary=f"{body.channel} consent {body.status} for {customer.display_name} ({body.method})",
        changes=body.model_dump(),
    )
    db.commit()
    db.refresh(consent)
    return _consent_read(consent, principal.full_name)


def consent_history(db: Session, principal: Principal, customer_id: uuid.UUID) -> list[ConsentRead]:
    principal.require_in_any_branch(P.CUSTOMERS_VIEW)
    customer = get_scoped(db, Customer, customer_id, principal.organisation_id)
    rows = db.execute(
        select(CustomerConsent, User.full_name)
        .outerjoin(User, User.id == CustomerConsent.recorded_by_user_id)
        .where(CustomerConsent.customer_id == customer.id)
        .order_by(CustomerConsent.recorded_at.desc())
    ).all()
    return [_consent_read(c, name) for c, name in rows]
