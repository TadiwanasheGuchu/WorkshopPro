import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, IdempotencyKey, Paging
from app.schemas.common import Page
from app.schemas.inventory import (
    AdjustmentCreate,
    CategoryInput,
    CategoryRead,
    LocationCreate,
    LocationRead,
    LocationUpdate,
    MinLevelUpdate,
    MovementKind,
    MovementRead,
    OperationRead,
    PartCreate,
    PartListItem,
    PartRead,
    PartUpdate,
    TransferCreate,
)
from app.services import inventory

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _replayed(response: Response, created: bool) -> None:
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"


# --------------------------------------------------------------------------- catalogue


@router.get("/categories", response_model=list[CategoryRead], summary="Part categories")
def list_categories(principal: CurrentPrincipal, db: DbSession) -> list[CategoryRead]:
    return inventory.list_categories(db, principal)


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a part category",
)
def create_category(
    body: CategoryInput, principal: CurrentPrincipal, db: DbSession
) -> CategoryRead:
    return inventory.save_category(db, principal, body)


@router.patch("/categories/{category_id}", response_model=CategoryRead, summary="Rename")
def rename_category(
    category_id: uuid.UUID, body: CategoryInput, principal: CurrentPrincipal, db: DbSession
) -> CategoryRead:
    return inventory.save_category(db, principal, body, category_id)


@router.get(
    "/parts",
    response_model=Page[PartListItem],
    summary="Parts catalogue",
    description="Stock figures cover the branches the caller can see. Cost price is "
    "returned only to users who manage the catalogue or adjust stock.",
)
def list_parts(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    category_id: uuid.UUID | None = None,
    low_stock: bool = False,
    include_archived: bool = False,
) -> Page[PartListItem]:
    items, total = inventory.list_parts(
        db,
        principal,
        paging,
        search=search,
        category_id=category_id,
        low_stock=low_stock,
        include_archived=include_archived,
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/parts", response_model=PartRead, status_code=status.HTTP_201_CREATED, summary="Add a part"
)
def create_part(body: PartCreate, principal: CurrentPrincipal, db: DbSession) -> PartRead:
    return inventory.create_part(db, principal, body)


@router.get("/parts/{part_id}", response_model=PartRead, summary="Part with stock by location")
def get_part(part_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> PartRead:
    return inventory.get_part(db, principal, part_id)


@router.patch("/parts/{part_id}", response_model=PartRead, summary="Edit a part")
def update_part(
    part_id: uuid.UUID, body: PartUpdate, principal: CurrentPrincipal, db: DbSession
) -> PartRead:
    return inventory.update_part(db, principal, part_id, body)


@router.post(
    "/parts/{part_id}/archive",
    response_model=PartRead,
    summary="Archive a part",
    description="Only parts with no stock on hand can be archived.",
)
def archive_part(part_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> PartRead:
    return inventory.set_archived(db, principal, part_id, True)


@router.post("/parts/{part_id}/restore", response_model=PartRead, summary="Restore a part")
def restore_part(part_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> PartRead:
    return inventory.set_archived(db, principal, part_id, False)


@router.put(
    "/parts/{part_id}/levels/{location_id}",
    response_model=PartRead,
    summary="Set the minimum (low-stock) level at a location",
)
def set_min_level(
    part_id: uuid.UUID,
    location_id: uuid.UUID,
    body: MinLevelUpdate,
    principal: CurrentPrincipal,
    db: DbSession,
) -> PartRead:
    return inventory.set_min_level(db, principal, part_id, location_id, body)


# --------------------------------------------------------------------------- locations


@router.get("/locations", response_model=list[LocationRead], summary="Stock locations")
def list_locations(
    principal: CurrentPrincipal, db: DbSession, branch_id: uuid.UUID | None = None
) -> list[LocationRead]:
    return inventory.list_locations(db, principal, branch_id)


@router.post(
    "/locations",
    response_model=LocationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a stock location",
)
def create_location(
    body: LocationCreate, principal: CurrentPrincipal, db: DbSession
) -> LocationRead:
    return inventory.create_location(db, principal, body)


@router.patch("/locations/{location_id}", response_model=LocationRead, summary="Rename")
def update_location(
    location_id: uuid.UUID, body: LocationUpdate, principal: CurrentPrincipal, db: DbSession
) -> LocationRead:
    return inventory.update_location(db, principal, location_id, body)


@router.post(
    "/locations/{location_id}/archive",
    response_model=LocationRead,
    summary="Archive an empty location",
)
def archive_location(
    location_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> LocationRead:
    return inventory.set_location_archived(db, principal, location_id, True)


@router.post("/locations/{location_id}/restore", response_model=LocationRead, summary="Restore")
def restore_location(
    location_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> LocationRead:
    return inventory.set_location_archived(db, principal, location_id, False)


# --------------------------------------------------------------------------- operations


@router.post(
    "/adjustments",
    response_model=OperationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Adjust stock (opening stock or stocktake correction)",
    description=(
        "Each line gives either the counted quantity or a signed change. A reason is "
        "required. Stock cannot go below zero or below what is reserved for jobs. "
        "Requires an Idempotency-Key."
    ),
)
def adjust(
    body: AdjustmentCreate,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> OperationRead:
    result, created = inventory.adjust(db, principal, body, idempotency_key)
    _replayed(response, created)
    return result


@router.post(
    "/transfers",
    response_model=OperationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Transfer stock between locations",
    description="Moves available (unreserved) stock. Requires an Idempotency-Key.",
)
def transfer(
    body: TransferCreate,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> OperationRead:
    result, created = inventory.transfer(db, principal, body, idempotency_key)
    _replayed(response, created)
    return result


@router.get(
    "/movements",
    response_model=Page[MovementRead],
    summary="Stock movement ledger",
    description="Newest first. Each line records the signed quantity and the balance after.",
)
def list_movements(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    part_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    kind: MovementKind | None = None,
    job_card_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Page[MovementRead]:
    items, total = inventory.list_movements(
        db,
        principal,
        paging,
        part_id=part_id,
        location_id=location_id,
        branch_id=branch_id,
        kind=kind,
        job_card_id=job_card_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)
