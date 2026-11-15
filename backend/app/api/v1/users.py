import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.api.deps import AppSettings, CurrentPrincipal, DbSession, Mailer, Paging
from app.schemas.common import Page
from app.schemas.user import (
    RoleAssignmentsUpdate,
    UserInvite,
    UserRead,
    UserStatus,
    UserUpdate,
)
from app.services import users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserRead], summary="List users")
def list_users(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status: UserStatus | None = None,
    role_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> Page[UserRead]:
    items, total = users.list_users(
        db, principal, paging, search=search, status=status, role_id=role_id, branch_id=branch_id
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user",
    description=(
        "Creates the account and emails a single-use invitation link. You can only assign "
        "roles whose permissions you hold yourself."
    ),
)
def invite_user(
    body: UserInvite,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    mailer: Mailer,
    background: BackgroundTasks,
) -> UserRead:
    user, email = users.invite_user(db, principal, settings, body)
    background.add_task(mailer.send, email)
    return user


@router.get("/{user_id}", response_model=UserRead, summary="User details")
def get_user(user_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> UserRead:
    return users.get_user(db, principal, user_id)


@router.patch("/{user_id}", response_model=UserRead, summary="Update a user")
def update_user(
    user_id: uuid.UUID, body: UserUpdate, principal: CurrentPrincipal, db: DbSession
) -> UserRead:
    return users.update_user(db, principal, user_id, body)


@router.post(
    "/{user_id}/deactivate",
    response_model=UserRead,
    summary="Deactivate a user",
    description="Signs the user out everywhere. Their history is kept.",
)
def deactivate_user(user_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> UserRead:
    return users.set_active(db, principal, user_id, False)


@router.post("/{user_id}/activate", response_model=UserRead, summary="Reactivate a user")
def activate_user(user_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> UserRead:
    return users.set_active(db, principal, user_id, True)


@router.post(
    "/{user_id}/resend-invitation",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend invitation email",
    description="Issues a new link; earlier invitation links stop working.",
)
def resend_invitation(
    user_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    mailer: Mailer,
    background: BackgroundTasks,
) -> None:
    email = users.resend_invitation(db, principal, settings, user_id)
    background.add_task(mailer.send, email)


@router.put(
    "/{user_id}/role-assignments",
    response_model=UserRead,
    summary="Replace a user's role assignments",
)
def set_role_assignments(
    user_id: uuid.UUID, body: RoleAssignmentsUpdate, principal: CurrentPrincipal, db: DbSession
) -> UserRead:
    return users.set_role_assignments(db, principal, user_id, body.role_assignments)
