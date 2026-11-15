import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession, Paging
from app.schemas.common import Page
from app.schemas.customer import (
    OwnershipRead,
    VehicleCreate,
    VehicleRead,
    VehicleTransfer,
    VehicleUpdate,
)
from app.services import vehicles

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get(
    "",
    response_model=Page[VehicleRead],
    summary="List vehicles",
    description=(
        "`search` matches registration and VIN ignoring spaces and hyphens "
        '("n12345w" finds "N 12345 W"), or make and model.'
    ),
)
def list_vehicles(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    customer_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> Page[VehicleRead]:
    items, total = vehicles.list_vehicles(
        db,
        principal,
        paging,
        search=search,
        customer_id=customer_id,
        include_archived=include_archived,
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "",
    response_model=VehicleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a vehicle",
    description=(
        "Needs a registration number or VIN / chassis number. Each must be unique among "
        "the organisation's active vehicles."
    ),
)
def create_vehicle(body: VehicleCreate, principal: CurrentPrincipal, db: DbSession) -> VehicleRead:
    return vehicles.create_vehicle(db, principal, body)


@router.get("/{vehicle_id}", response_model=VehicleRead, summary="Vehicle details")
def get_vehicle(vehicle_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> VehicleRead:
    return vehicles.get_vehicle(db, principal, vehicle_id)


@router.patch(
    "/{vehicle_id}",
    response_model=VehicleRead,
    summary="Update a vehicle",
    description="Lowering the odometer requires `odometer_correction_reason` (422 otherwise).",
)
def update_vehicle(
    vehicle_id: uuid.UUID, body: VehicleUpdate, principal: CurrentPrincipal, db: DbSession
) -> VehicleRead:
    return vehicles.update_vehicle(db, principal, vehicle_id, body)


@router.post(
    "/{vehicle_id}/transfer",
    response_model=VehicleRead,
    summary="Transfer to another customer",
    description="Closes the current ownership record and opens a new one.",
)
def transfer_vehicle(
    vehicle_id: uuid.UUID, body: VehicleTransfer, principal: CurrentPrincipal, db: DbSession
) -> VehicleRead:
    return vehicles.transfer_vehicle(db, principal, vehicle_id, body)


@router.get(
    "/{vehicle_id}/ownership",
    response_model=list[OwnershipRead],
    summary="Ownership history",
)
def ownership_history(
    vehicle_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[OwnershipRead]:
    return vehicles.ownership_history(db, principal, vehicle_id)


@router.post("/{vehicle_id}/archive", response_model=VehicleRead, summary="Archive a vehicle")
def archive_vehicle(
    vehicle_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> VehicleRead:
    return vehicles.set_archived(db, principal, vehicle_id, True)


@router.post("/{vehicle_id}/restore", response_model=VehicleRead, summary="Restore a vehicle")
def restore_vehicle(
    vehicle_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> VehicleRead:
    return vehicles.set_archived(db, principal, vehicle_id, False)
