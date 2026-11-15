import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession, Paging
from app.schemas.branch import (
    BranchCreate,
    BranchDetail,
    BranchRead,
    BranchUpdate,
    OperatingHoursRead,
    OperatingHoursUpdate,
    ServiceBayCreate,
    ServiceBayRead,
    ServiceBayUpdate,
)
from app.schemas.common import Page
from app.services import branches

router = APIRouter(prefix="/branches", tags=["branches"])


def _detail(db: DbSession, branch: object) -> BranchDetail:
    hours = branches.get_operating_hours(db, branch)  # type: ignore[arg-type]
    return BranchDetail.model_validate(
        {
            **BranchRead.model_validate(branch).model_dump(),
            "operating_hours": [OperatingHoursRead.model_validate(h) for h in hours],
        }
    )


@router.get(
    "",
    response_model=Page[BranchRead],
    summary="List branches",
    description="Users with branch-scoped access only see their own branches.",
)
def list_branches(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    include_archived: bool = False,
) -> Page[BranchRead]:
    items, total = branches.list_branches(
        db, principal, paging, search=search, include_archived=include_archived
    )
    return Page(
        items=[BranchRead.model_validate(b) for b in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "",
    response_model=BranchDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a branch",
    description="Requires an organisation-wide `branches.manage` grant. Default hours are applied.",
)
def create_branch(body: BranchCreate, principal: CurrentPrincipal, db: DbSession) -> BranchDetail:
    return _detail(db, branches.create_branch(db, principal, body))


@router.get("/{branch_id}", response_model=BranchDetail, summary="Branch details")
def get_branch(branch_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> BranchDetail:
    return _detail(db, branches.get_branch(db, principal, branch_id))


@router.patch("/{branch_id}", response_model=BranchDetail, summary="Update a branch")
def update_branch(
    branch_id: uuid.UUID, body: BranchUpdate, principal: CurrentPrincipal, db: DbSession
) -> BranchDetail:
    return _detail(db, branches.update_branch(db, principal, branch_id, body))


@router.post("/{branch_id}/archive", response_model=BranchDetail, summary="Archive a branch")
def archive_branch(
    branch_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> BranchDetail:
    return _detail(db, branches.set_archived(db, principal, branch_id, True))


@router.post("/{branch_id}/restore", response_model=BranchDetail, summary="Restore a branch")
def restore_branch(
    branch_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> BranchDetail:
    return _detail(db, branches.set_archived(db, principal, branch_id, False))


@router.put(
    "/{branch_id}/operating-hours",
    response_model=list[OperatingHoursRead],
    summary="Replace operating hours",
    description="Provide all seven weekdays (0 = Monday).",
)
def set_operating_hours(
    branch_id: uuid.UUID, body: OperatingHoursUpdate, principal: CurrentPrincipal, db: DbSession
) -> list[OperatingHoursRead]:
    hours = branches.set_operating_hours(db, principal, branch_id, body)
    return [OperatingHoursRead.model_validate(h) for h in hours]


@router.get(
    "/{branch_id}/service-bays", response_model=list[ServiceBayRead], summary="Service bays"
)
def list_service_bays(
    branch_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[ServiceBayRead]:
    return [
        ServiceBayRead.model_validate(b)
        for b in branches.list_service_bays(db, principal, branch_id)
    ]


@router.post(
    "/{branch_id}/service-bays",
    response_model=ServiceBayRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a service bay",
)
def create_service_bay(
    branch_id: uuid.UUID, body: ServiceBayCreate, principal: CurrentPrincipal, db: DbSession
) -> ServiceBayRead:
    return ServiceBayRead.model_validate(
        branches.create_service_bay(db, principal, branch_id, body)
    )


@router.patch(
    "/{branch_id}/service-bays/{bay_id}",
    response_model=ServiceBayRead,
    summary="Update a service bay",
    description="Set `is_active` to false to retire a bay; bays are never deleted.",
)
def update_service_bay(
    branch_id: uuid.UUID,
    bay_id: uuid.UUID,
    body: ServiceBayUpdate,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ServiceBayRead:
    return ServiceBayRead.model_validate(
        branches.update_service_bay(db, principal, branch_id, bay_id, body)
    )
