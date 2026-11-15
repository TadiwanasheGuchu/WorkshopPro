"""Vehicles and ownership history."""

import uuid
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import Customer, Vehicle, VehicleOwnership
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.customer import (
    CustomerBrief,
    OwnershipRead,
    VehicleCreate,
    VehicleRead,
    VehicleTransfer,
    VehicleUpdate,
    registration_key,
)
from app.services import audit
from app.services.common import get_scoped, paginate


class OdometerDecreaseError(AppError):
    status_code = 422
    code = "odometer_decrease"


def _duplicate_error(exc: IntegrityError) -> ConflictError:
    which = "VIN / chassis number" if "vin" in str(exc.orig) else "registration number"
    return ConflictError(f"Another active vehicle already has this {which}.")


def label(v: Vehicle) -> str:
    ident = v.registration_number or v.vin or "unregistered"
    return f"{ident} ({v.make} {v.model})"


def _to_read(db: Session, vehicles: list[Vehicle]) -> list[VehicleRead]:
    ids = {v.customer_id for v in vehicles}
    names = (
        dict(
            db.execute(select(Customer.id, Customer.display_name).where(Customer.id.in_(ids))).all()
        )
        if ids
        else {}
    )
    return [
        VehicleRead(
            id=v.id,
            customer=CustomerBrief(id=v.customer_id, display_name=names.get(v.customer_id, "")),
            registration_number=v.registration_number,
            vin=v.vin,
            engine_number=v.engine_number,
            make=v.make,
            model=v.model,
            variant=v.variant,
            year=v.year,
            fuel_type=v.fuel_type,  # type: ignore[arg-type]
            transmission=v.transmission,  # type: ignore[arg-type]
            colour=v.colour,
            odometer_km=v.odometer_km,
            odometer_recorded_at=v.odometer_recorded_at,
            existing_damage=v.existing_damage,
            notes=v.notes,
            archived_at=v.archived_at,
            created_at=v.created_at,
        )
        for v in vehicles
    ]


def _active_customer(db: Session, principal: Principal, customer_id: uuid.UUID) -> Customer:
    try:
        customer = get_scoped(db, Customer, customer_id, principal.organisation_id)
    except NotFoundError as exc:
        raise NotFoundError("Customer not found.") from exc
    if customer.archived_at is not None:
        raise ConflictError("This customer is archived. Restore them first.")
    return customer


def list_vehicles(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    search: str | None = None,
    customer_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> tuple[list[VehicleRead], int]:
    principal.require_in_any_branch(P.VEHICLES_VIEW)
    stmt = select(Vehicle).where(Vehicle.organisation_id == principal.organisation_id)
    if not include_archived:
        stmt = stmt.where(Vehicle.archived_at.is_(None))
    if customer_id:
        stmt = stmt.where(Vehicle.customer_id == customer_id)
    if search:
        term = search.strip()
        key = registration_key(term)
        pattern = f"%{term}%"
        stmt = stmt.where(
            or_(
                *(
                    [Vehicle.registration_key.contains(key), Vehicle.vin.contains(key)]
                    if key
                    else []
                ),
                (Vehicle.make + " " + Vehicle.model).ilike(pattern),
            )
        )
    items, total = paginate(
        db, stmt.order_by(Vehicle.registration_key.nulls_last(), Vehicle.id), params
    )
    return _to_read(db, items), total


def get_vehicle(db: Session, principal: Principal, vehicle_id: uuid.UUID) -> VehicleRead:
    principal.require_in_any_branch(P.VEHICLES_VIEW)
    return _to_read(db, [get_scoped(db, Vehicle, vehicle_id, principal.organisation_id)])[0]


def ownership_history(
    db: Session, principal: Principal, vehicle_id: uuid.UUID
) -> list[OwnershipRead]:
    principal.require_in_any_branch(P.VEHICLES_VIEW)
    vehicle = get_scoped(db, Vehicle, vehicle_id, principal.organisation_id)
    rows = db.execute(
        select(VehicleOwnership, Customer.display_name)
        .join(Customer, Customer.id == VehicleOwnership.customer_id)
        .where(VehicleOwnership.vehicle_id == vehicle.id)
        .order_by(VehicleOwnership.started_at.desc())
    ).all()
    return [
        OwnershipRead(
            customer=CustomerBrief(id=o.customer_id, display_name=name),
            started_at=o.started_at,
            ended_at=o.ended_at,
            note=o.note,
        )
        for o, name in rows
    ]


def create_vehicle(db: Session, principal: Principal, body: VehicleCreate) -> VehicleRead:
    principal.require_in_any_branch(P.VEHICLES_MANAGE)
    customer = _active_customer(db, principal, body.customer_id)
    data = body.model_dump()
    vehicle = Vehicle(
        organisation_id=principal.organisation_id,
        registration_key=registration_key(body.registration_number)
        if body.registration_number
        else None,
        odometer_recorded_at=utcnow() if body.odometer_km is not None else None,
        **data,
    )
    db.add(vehicle)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate_error(exc) from exc
    db.add(
        VehicleOwnership(
            organisation_id=principal.organisation_id,
            vehicle_id=vehicle.id,
            customer_id=customer.id,
            recorded_by_user_id=principal.user_id,
            note="Registered",
        )
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="vehicle.created",
        entity_type="vehicle",
        entity_id=vehicle.id,
        summary=f"Vehicle {label(vehicle)} registered for {customer.display_name}",
    )
    db.commit()
    return _to_read(db, [vehicle])[0]


def update_vehicle(
    db: Session, principal: Principal, vehicle_id: uuid.UUID, body: VehicleUpdate
) -> VehicleRead:
    principal.require_in_any_branch(P.VEHICLES_MANAGE)
    vehicle = get_scoped(db, Vehicle, vehicle_id, principal.organisation_id)
    data = body.changes()
    reason = data.pop("odometer_correction_reason", None)

    if "odometer_km" in data and data["odometer_km"] is not None:
        current = vehicle.odometer_km
        if current is not None and data["odometer_km"] < current and not reason:
            raise OdometerDecreaseError(
                f"The odometer was last recorded at {current:,} km. Give a reason to lower it.",
                details={"current_odometer_km": current},
            )
    changes: dict[str, list[Any]] = {}
    for key, value in data.items():
        old = getattr(vehicle, key)
        if old != value:
            changes[key] = [old, value]
            setattr(vehicle, key, value)
    if "registration_number" in changes:
        vehicle.registration_key = (
            registration_key(vehicle.registration_number) if vehicle.registration_number else None
        )
    if "odometer_km" in changes:
        vehicle.odometer_recorded_at = utcnow()
        if reason:
            changes["odometer_correction_reason"] = [None, reason]
    if not vehicle.registration_number and not vehicle.vin:
        raise ConflictError("A vehicle needs a registration number or a VIN / chassis number.")
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate_error(exc) from exc
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="vehicle.updated",
            entity_type="vehicle",
            entity_id=vehicle.id,
            summary=f"Vehicle {label(vehicle)} updated",
            changes=changes,
        )
    db.commit()
    return _to_read(db, [vehicle])[0]


def transfer_vehicle(
    db: Session, principal: Principal, vehicle_id: uuid.UUID, body: VehicleTransfer
) -> VehicleRead:
    principal.require_in_any_branch(P.VEHICLES_MANAGE)
    vehicle = get_scoped(db, Vehicle, vehicle_id, principal.organisation_id)
    if vehicle.archived_at is not None:
        raise ConflictError("Restore this vehicle before transferring it.")
    new_owner = _active_customer(db, principal, body.customer_id)
    if new_owner.id == vehicle.customer_id:
        raise ConflictError("The vehicle already belongs to this customer.")
    now = utcnow()
    db.execute(
        update(VehicleOwnership)
        .where(VehicleOwnership.vehicle_id == vehicle.id, VehicleOwnership.ended_at.is_(None))
        .values(ended_at=now)
    )
    old_owner_id = vehicle.customer_id
    vehicle.customer_id = new_owner.id
    db.add(
        VehicleOwnership(
            organisation_id=principal.organisation_id,
            vehicle_id=vehicle.id,
            customer_id=new_owner.id,
            started_at=now,
            recorded_by_user_id=principal.user_id,
            note=body.note,
        )
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="vehicle.transferred",
        entity_type="vehicle",
        entity_id=vehicle.id,
        summary=f"Vehicle {label(vehicle)} transferred to {new_owner.display_name}",
        changes={"customer_id": [old_owner_id, new_owner.id], "note": body.note},
    )
    db.commit()
    return _to_read(db, [vehicle])[0]


def set_archived(
    db: Session, principal: Principal, vehicle_id: uuid.UUID, archived: bool
) -> VehicleRead:
    principal.require_in_any_branch(P.VEHICLES_MANAGE)
    vehicle = get_scoped(db, Vehicle, vehicle_id, principal.organisation_id)
    if archived == (vehicle.archived_at is not None):
        return _to_read(db, [vehicle])[0]
    if not archived:
        _active_customer(db, principal, vehicle.customer_id)
    vehicle.archived_at = utcnow() if archived else None
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Another active vehicle now uses this registration or VIN. "
            "Archive or correct it before restoring this one."
        ) from exc
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="vehicle.archived" if archived else "vehicle.restored",
        entity_type="vehicle",
        entity_id=vehicle.id,
        summary=f"Vehicle {label(vehicle)} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return _to_read(db, [vehicle])[0]
