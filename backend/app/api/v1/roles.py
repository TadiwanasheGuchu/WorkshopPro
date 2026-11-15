import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession
from app.permissions.catalogue import PERMISSIONS, P
from app.schemas.user import PermissionRead, RoleCreate, RoleRead, RoleUpdate
from app.services import roles

router = APIRouter(tags=["roles"])


@router.get(
    "/permissions",
    response_model=list[PermissionRead],
    summary="Permission catalogue",
    description="Every permission that can be granted to a role.",
)
def list_permissions(principal: CurrentPrincipal) -> list[PermissionRead]:
    principal.require(P.USERS_VIEW)
    return [
        PermissionRead(
            code=p.code, module=p.module, label=p.label, description=p.description, scope=p.scope
        )
        for p in PERMISSIONS
    ]


@router.get("/roles", response_model=list[RoleRead], summary="List roles")
def list_roles(
    principal: CurrentPrincipal, db: DbSession, include_archived: bool = False
) -> list[RoleRead]:
    return roles.list_roles(db, principal, include_archived=include_archived)


@router.post(
    "/roles",
    response_model=RoleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a role",
    description="You can only include permissions you hold yourself.",
)
def create_role(body: RoleCreate, principal: CurrentPrincipal, db: DbSession) -> RoleRead:
    return roles.create_role(db, principal, body)


@router.get("/roles/{role_id}", response_model=RoleRead, summary="Role details")
def get_role(role_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> RoleRead:
    return roles.get_role(db, principal, role_id)


@router.patch("/roles/{role_id}", response_model=RoleRead, summary="Update a role")
def update_role(
    role_id: uuid.UUID, body: RoleUpdate, principal: CurrentPrincipal, db: DbSession
) -> RoleRead:
    return roles.update_role(db, principal, role_id, body)


@router.post(
    "/roles/{role_id}/archive",
    response_model=RoleRead,
    summary="Archive a role",
    description="Only roles with no current assignments can be archived.",
)
def archive_role(role_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> RoleRead:
    return roles.set_archived(db, principal, role_id, True)


@router.post("/roles/{role_id}/restore", response_model=RoleRead, summary="Restore a role")
def restore_role(role_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> RoleRead:
    return roles.set_archived(db, principal, role_id, False)
