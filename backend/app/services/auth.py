"""Authentication: sessions, sign-in, password reset, invitations, password change."""

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from redis import Redis
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, NotAuthenticatedError
from app.core.security import (
    hash_password,
    hash_token,
    new_token,
    password_needs_rehash,
    verify_password,
)
from app.core.time import utcnow
from app.integrations.email import OutgoingEmail
from app.models import Organisation, User, UserSession, UserToken
from app.permissions.principal import Principal
from app.services import audit, emails, rate_limit

logger = logging.getLogger(__name__)

# Write last_seen_at at most this often, so ordinary requests don't all write.
_TOUCH_INTERVAL = timedelta(minutes=5)


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"


class InvalidTokenError(AppError):
    status_code = 400
    code = "invalid_token"


@dataclass(frozen=True)
class NewSession:
    session: UserSession
    token: str


# --------------------------------------------------------------------------- sessions


def create_session(
    db: Session, user: User, settings: Settings, *, ip: str | None, user_agent: str | None
) -> NewSession:
    now = utcnow()
    token = new_token()
    session = UserSession(
        organisation_id=user.organisation_id,
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=new_token(),
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_timeout_hours),
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(session)
    db.flush()
    return NewSession(session=session, token=token)


def resolve_session(db: Session, token: str, settings: Settings) -> tuple[UserSession, User]:
    """Return the active session and user for a cookie token, or raise 401."""
    now = utcnow()
    row = db.execute(
        select(UserSession, User, Organisation.is_active)
        .join(User, User.id == UserSession.user_id)
        .join(Organisation, Organisation.id == User.organisation_id)
        .where(UserSession.token_hash == hash_token(token))
    ).one_or_none()
    if row is None:
        raise NotAuthenticatedError("Please sign in.")
    session, user, org_active = row
    idle_deadline = session.last_seen_at + timedelta(minutes=settings.session_idle_timeout_minutes)
    if (
        session.revoked_at is not None
        or session.expires_at <= now
        or idle_deadline <= now
        or not user.is_active
        or not org_active
    ):
        raise NotAuthenticatedError("Your session has ended. Please sign in again.")
    if now - session.last_seen_at > _TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return session, user


def csrf_matches_session(session: UserSession, header_value: str | None) -> bool:
    return bool(header_value) and hmac.compare_digest(
        session.csrf_token.encode(), (header_value or "").encode()
    )


def revoke_user_sessions(
    db: Session, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None
) -> None:
    stmt = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    db.execute(stmt.values(revoked_at=utcnow()))


# --------------------------------------------------------------------------- sign-in


def login(
    db: Session,
    redis: Redis,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
) -> NewSession:
    limits = settings.rate_limit_enabled
    rate_limit.enforce(
        redis,
        "login-ip",
        ip or "unknown",
        limit=settings.login_attempts_per_ip,
        window_seconds=settings.login_window_seconds,
        enabled=limits,
    )
    rate_limit.enforce(
        redis,
        "login-email",
        email,
        limit=settings.login_attempts_per_email,
        window_seconds=settings.login_window_seconds,
        enabled=limits,
    )

    row = db.execute(
        select(User, Organisation.is_active)
        .join(Organisation, Organisation.id == User.organisation_id)
        .where(User.email == email)
    ).one_or_none()
    user, org_active = row if row else (None, False)

    password_ok = verify_password(user.password_hash if user else None, password)
    if user is None or not password_ok or not user.is_active or not org_active:
        if user is not None:
            reason = (
                "wrong_password"
                if not password_ok
                else "user_inactive"
                if not user.is_active
                else "organisation_inactive"
            )
            audit.record(
                db,
                organisation_id=user.organisation_id,
                actor_user_id=user.id,
                action="auth.login_failed",
                entity_type="user",
                entity_id=user.id,
                summary=f"Failed sign-in for {user.email}",
                changes={"reason": reason},
            )
            db.commit()
        else:
            logger.info("login_unknown_email")
        # One message for every failure so responses don't reveal which accounts exist.
        raise InvalidCredentialsError("Email or password is incorrect.")

    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    new = create_session(db, user, settings, ip=ip, user_agent=user_agent)
    audit.record(
        db,
        organisation_id=user.organisation_id,
        actor_user_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} signed in",
    )
    db.commit()
    rate_limit.reset(redis, "login-email", email)
    return new


def logout(db: Session, principal: Principal) -> None:
    if principal.session_id is None:
        return
    db.execute(
        update(UserSession)
        .where(UserSession.id == principal.session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="auth.logout",
        entity_type="user",
        entity_id=principal.user_id,
        summary=f"{principal.full_name} signed out",
    )
    db.commit()


# --------------------------------------------------------------------------- tokens


def issue_user_token(
    db: Session,
    user: User,
    purpose: str,
    lifetime: timedelta,
    *,
    created_by: uuid.UUID | None = None,
) -> str:
    """Create a single-use token, revoking earlier unused tokens of the same purpose."""
    now = utcnow()
    db.execute(
        update(UserToken)
        .where(
            UserToken.user_id == user.id,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
            UserToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token = new_token()
    db.add(
        UserToken(
            organisation_id=user.organisation_id,
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=now + lifetime,
            created_by_user_id=created_by,
        )
    )
    return token


def _consume_target(db: Session, token: str, purpose: str, *, lock: bool) -> tuple[UserToken, User]:
    stmt = (
        select(UserToken, User)
        .join(User, User.id == UserToken.user_id)
        .where(UserToken.token_hash == hash_token(token), UserToken.purpose == purpose)
    )
    if lock:
        stmt = stmt.with_for_update(of=UserToken)
    row = db.execute(stmt).one_or_none()
    invalid = InvalidTokenError("This link is invalid or has expired. Request a new one.")
    if row is None:
        raise invalid
    user_token, user = row
    if (
        user_token.used_at is not None
        or user_token.revoked_at is not None
        or user_token.expires_at <= utcnow()
        or not user.is_active
    ):
        raise invalid
    return user_token, user


def inspect_token(db: Session, token: str, purpose: str) -> tuple[User, Organisation]:
    _, user = _consume_target(db, token, purpose, lock=False)
    org = db.get_one(Organisation, user.organisation_id)
    return user, org


def request_password_reset(
    db: Session, redis: Redis, settings: Settings, *, email: str, ip: str | None
) -> OutgoingEmail | None:
    """Always succeeds from the caller's view; returns an email to send if applicable."""
    rate_limit.enforce(
        redis,
        "reset-ip",
        ip or "unknown",
        limit=settings.password_reset_requests_per_ip,
        window_seconds=settings.password_reset_window_seconds,
        enabled=settings.rate_limit_enabled,
    )
    # Per-email limit is silent: exceeding it must not reveal that the account exists.
    if settings.rate_limit_enabled and not rate_limit.hit(
        redis, "reset-email", email, limit=3, window_seconds=settings.password_reset_window_seconds
    ):
        return None

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or user.password_hash is None:
        return None
    token = issue_user_token(
        db, user, "password_reset", timedelta(minutes=settings.password_reset_token_minutes)
    )
    audit.record(
        db,
        organisation_id=user.organisation_id,
        actor_user_id=user.id,
        action="auth.password_reset_requested",
        entity_type="user",
        entity_id=user.id,
        summary=f"Password reset requested for {user.email}",
    )
    db.commit()
    return emails.password_reset_email(to=user.email, full_name=user.full_name, token=token)


def _set_password(user: User, password: str) -> None:
    now = utcnow()
    user.password_hash = hash_password(password)
    user.password_changed_at = now


def confirm_password_reset(db: Session, *, token: str, new_password: str) -> None:
    user_token, user = _consume_target(db, token, "password_reset", lock=True)
    _set_password(user, new_password)
    user_token.used_at = utcnow()
    revoke_user_sessions(db, user.id)
    audit.record(
        db,
        organisation_id=user.organisation_id,
        actor_user_id=user.id,
        action="auth.password_reset_completed",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} reset their password; all sessions signed out",
    )
    db.commit()


def accept_invitation(db: Session, *, token: str, password: str) -> None:
    user_token, user = _consume_target(db, token, "invitation", lock=True)
    now = utcnow()
    _set_password(user, password)
    user.activated_at = now
    user_token.used_at = now
    audit.record(
        db,
        organisation_id=user.organisation_id,
        actor_user_id=user.id,
        action="user.invitation_accepted",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} accepted their invitation",
    )
    db.commit()


def change_password(
    db: Session, principal: Principal, *, current_password: str, new_password: str
) -> None:
    user = db.get_one(User, principal.user_id)
    if not verify_password(user.password_hash, current_password):
        raise InvalidCredentialsError("Current password is incorrect.")
    _set_password(user, new_password)
    revoke_user_sessions(db, user.id, except_id=principal.session_id)
    audit.record(
        db,
        organisation_id=user.organisation_id,
        actor=principal,
        action="auth.password_changed",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} changed their password; other sessions signed out",
    )
    db.commit()
