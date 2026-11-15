import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.permissions.catalogue import Scope
from app.schemas.common import Email, Name, OptionalStr, ReadSchema, Schema, UpdateSchema

UserStatus = Literal["active", "invited", "deactivated"]


class RoleAssignmentInput(Schema):
    role_id: uuid.UUID
    branch_id: uuid.UUID | None = Field(
        None, description="Null grants the role in all branches (organisation-wide)."
    )


def _unique_assignments(assignments: list[RoleAssignmentInput]) -> None:
    keys = [(a.role_id, a.branch_id) for a in assignments]
    if len(keys) != len(set(keys)):
        raise ValueError("Each role and branch combination may be listed only once.")


class RoleAssignmentRead(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    role_name: str
    branch_id: uuid.UUID | None
    branch_name: str | None


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    status: UserStatus
    is_owner: bool
    last_login_at: datetime | None
    invited_at: datetime | None
    activated_at: datetime | None
    created_at: datetime
    role_assignments: list[RoleAssignmentRead]


class UserInvite(Schema):
    email: Email
    full_name: Name
    phone: OptionalStr = Field(None, max_length=50)
    role_assignments: list[RoleAssignmentInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique_assignments(self.role_assignments)
        return self


class UserUpdate(UpdateSchema):
    non_nullable = frozenset({"full_name", "email"})

    full_name: Name | None = None
    email: Email | None = None
    phone: OptionalStr = Field(None, max_length=50)


class RoleAssignmentsUpdate(Schema):
    role_assignments: list[RoleAssignmentInput] = Field(max_length=50)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique_assignments(self.role_assignments)
        return self


# --------------------------------------------------------------------------- roles


class PermissionRead(BaseModel):
    code: str
    module: str
    label: str
    description: str
    scope: Scope


class RoleRead(ReadSchema):
    id: uuid.UUID
    name: str
    description: str | None
    is_owner: bool
    template_key: str | None
    archived_at: datetime | None
    permissions: list[str]
    user_count: int


RoleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RoleCreate(Schema):
    name: RoleName
    description: OptionalStr = Field(None, max_length=300)
    permissions: list[str] = Field(default_factory=list, max_length=200)


class RoleUpdate(UpdateSchema):
    non_nullable = frozenset({"name", "permissions"})

    name: RoleName | None = None
    description: OptionalStr = Field(None, max_length=300)
    permissions: list[str] | None = Field(None, max_length=200)
