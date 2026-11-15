import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Email, Password, Schema


class LoginRequest(Schema):
    email: Email
    # Length is not validated on login beyond a sane maximum; the hash check decides.
    password: str = Field(min_length=1, max_length=256)


class PasswordResetRequest(Schema):
    email: Email


class TokenBody(Schema):
    token: str = Field(min_length=20, max_length=100)


class PasswordResetConfirm(TokenBody):
    new_password: Password


class InvitationAccept(TokenBody):
    password: Password


class ChangePasswordRequest(Schema):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: Password


class TokenInfo(BaseModel):
    purpose: Literal["password_reset", "invitation"]
    email: str
    full_name: str
    organisation_name: str


class BranchSummary(BaseModel):
    id: uuid.UUID
    name: str
    code: str


class OrganisationSummary(BaseModel):
    id: uuid.UUID
    name: str
    currency_code: str
    timezone: str
    date_format: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_owner: bool
    organisation: OrganisationSummary
    # Permissions granted organisation-wide.
    permissions: list[str]
    # Additional permissions granted only for specific branches.
    branch_permissions: dict[uuid.UUID, list[str]]
    # Branches the user works in (all active branches for organisation-wide roles).
    branches: list[BranchSummary]
