from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import (
    AppSettings,
    CurrentPrincipal,
    DbSession,
    Mailer,
    RedisClient,
    client_ip,
)
from app.core.config import Settings
from app.core.errors import NotAuthenticatedError
from app.core.security import CSRF_COOKIE, SESSION_COOKIE, new_token
from app.models import Branch, Organisation, OrganisationSettings
from app.schemas.auth import (
    BranchSummary,
    ChangePasswordRequest,
    InvitationAccept,
    LoginRequest,
    MeResponse,
    OrganisationSummary,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenBody,
    TokenInfo,
)
from app.services import auth, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


class CsrfResponse(BaseModel):
    csrf_token: str


def _set_cookie(
    response: Response, settings: Settings, name: str, value: str, *, http_only: bool
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=settings.session_absolute_timeout_hours * 3600,
        httponly=http_only,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response, settings: Settings) -> None:
    for name, http_only in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(
            name, path="/", secure=settings.secure_cookies, httponly=http_only, samesite="lax"
        )


@router.get(
    "/csrf",
    response_model=CsrfResponse,
    summary="Get a CSRF token",
    description=(
        "Sets the `wp_csrf` cookie if missing and returns its value. Send it back in the "
        "`X-CSRF-Token` header on every POST/PUT/PATCH/DELETE."
    ),
)
def csrf(
    request: Request, response: Response, db: DbSession, settings: AppSettings
) -> CsrfResponse:
    token = None
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        try:
            session, _ = auth.resolve_session(db, session_token, settings)
            token = session.csrf_token
        except NotAuthenticatedError:
            pass
    token = token or request.cookies.get(CSRF_COOKIE) or new_token()
    _set_cookie(response, settings, CSRF_COOKIE, token, http_only=False)
    return CsrfResponse(csrf_token=token)


@router.post(
    "/login",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign in",
    description="Creates a session and sets the `wp_session` (HTTP-only) and `wp_csrf` cookies.",
    responses={401: {"description": "Invalid credentials"}, 429: {"description": "Rate limited"}},
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
) -> None:
    new = auth.login(
        db,
        redis,
        settings,
        email=body.email,
        password=body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:300] or None,
    )
    _set_cookie(response, settings, SESSION_COOKIE, new.token, http_only=True)
    _set_cookie(response, settings, CSRF_COOKIE, new.session.csrf_token, http_only=False)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def logout(
    principal: CurrentPrincipal, response: Response, db: DbSession, settings: AppSettings
) -> None:
    auth.logout(db, principal)
    _clear_cookies(response, settings)


@router.get("/me", response_model=MeResponse, summary="Current user, permissions and branches")
def me(principal: CurrentPrincipal, db: DbSession) -> MeResponse:
    org = db.get_one(Organisation, principal.organisation_id)
    org_settings = db.get_one(OrganisationSettings, principal.organisation_id)
    stmt = select(Branch).where(
        Branch.organisation_id == principal.organisation_id, Branch.archived_at.is_(None)
    )
    if not principal.has_org_wide_role:
        stmt = stmt.where(Branch.id.in_(principal.assigned_branch_ids))
    branches = db.scalars(stmt.order_by(Branch.name))
    return MeResponse(
        id=principal.user_id,
        email=principal.email,
        full_name=principal.full_name,
        is_owner=principal.is_owner,
        organisation=OrganisationSummary(
            id=org.id,
            name=org.name,
            currency_code=org_settings.currency_code,
            timezone=org_settings.timezone,
            date_format=org_settings.date_format,
        ),
        permissions=sorted(principal.effective_org_permissions()),
        branch_permissions={b: sorted(p) for b, p in principal.branch_permissions.items()},
        branches=[BranchSummary(id=b.id, name=b.name, code=b.code) for b in branches],
    )


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password",
    description="Requires the current password. Signs out all other sessions.",
)
def change_password(
    body: ChangePasswordRequest, principal: CurrentPrincipal, db: DbSession
) -> None:
    auth.change_password(
        db, principal, current_password=body.current_password, new_password=body.new_password
    )


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset email",
    description=(
        "Always returns 202, whether or not the email belongs to an account, so the "
        "endpoint cannot be used to discover accounts."
    ),
)
def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
    mailer: Mailer,
) -> None:
    email = auth.request_password_reset(
        db, redis, settings, email=body.email, ip=client_ip(request)
    )
    if email is not None:
        background.add_task(mailer.send, email)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password with a reset token",
    description="Tokens are single-use. All of the user's sessions are signed out.",
)
def confirm_password_reset(body: PasswordResetConfirm, db: DbSession) -> None:
    auth.confirm_password_reset(db, token=body.token, new_password=body.new_password)


@router.post(
    "/tokens/inspect",
    response_model=TokenInfo,
    summary="Check an invitation or reset token before showing the form",
)
def inspect_token(
    body: TokenBody,
    purpose: Literal["invitation", "password_reset"],
    request: Request,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
) -> TokenInfo:
    rate_limit.enforce(
        redis,
        "token-inspect",
        client_ip(request) or "unknown",
        limit=60,
        window_seconds=900,
        enabled=settings.rate_limit_enabled,
    )
    user, org = auth.inspect_token(db, body.token, purpose)
    return TokenInfo(
        purpose=purpose,
        email=user.email,
        full_name=user.full_name,
        organisation_name=org.name,
    )


@router.post(
    "/invitations/accept",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Accept an invitation and set a password",
)
def accept_invitation(body: InvitationAccept, db: DbSession) -> None:
    auth.accept_invitation(db, token=body.token, password=body.password)
