import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A staff account. Email is globally unique so sign-in needs only email + password
    (see docs/decisions/0004-identity-and-sessions.md)."""

    __tablename__ = "users"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    # Null until the user accepts their invitation and sets a password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name"),
        # Exactly one owner role per organisation.
        Index(
            "uq_roles_one_owner_role",
            "organisation_id",
            unique=True,
            postgresql_where=text("is_owner"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300))
    # Set for roles seeded from a template; lets data migrations grant new permissions.
    template_key: Mapped[str | None] = mapped_column(String(50))
    # The owner role implicitly holds every permission and cannot be edited.
    is_owner: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    # Validated against app.permissions.catalogue in the service layer.
    permission: Mapped[str] = mapped_column(String(100), primary_key=True)


class UserRoleAssignment(UUIDPrimaryKeyMixin, Base):
    """Grants a role to a user, organisation-wide (branch_id NULL) or for one branch."""

    __tablename__ = "user_role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "branch_id", postgresql_nulls_not_distinct=True),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class UserSession(UUIDPrimaryKeyMixin, Base):
    """Server-side browser session. The cookie carries a random token; only its hash
    is stored here."""

    __tablename__ = "user_sessions"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(300))


class UserToken(UUIDPrimaryKeyMixin, Base):
    """Single-use, expiring token for password reset or invitation acceptance."""

    __tablename__ = "user_tokens"
    __table_args__ = (
        CheckConstraint("purpose IN ('password_reset', 'invitation')", name="purpose_valid"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
