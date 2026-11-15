"""Shared API dependencies: database, Redis, settings, authentication."""

from typing import Annotated

from fastapi import Depends, Request
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.context import valid_ip
from app.core.errors import NotAuthenticatedError, PermissionDeniedError
from app.core.middleware import SAFE_METHODS
from app.core.redis import get_redis
from app.core.security import CSRF_HEADER, SESSION_COOKIE
from app.db.session import get_db
from app.integrations.email import EmailSender, get_email_sender
from app.permissions.principal import Principal, load_principal
from app.schemas.common import PageParams
from app.services import auth

DbSession = Annotated[Session, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Mailer = Annotated[EmailSender, Depends(get_email_sender)]
Paging = Annotated[PageParams, Depends()]


def get_principal(request: Request, db: DbSession, settings: AppSettings) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise NotAuthenticatedError("Please sign in.")
    session, user = auth.resolve_session(db, token, settings)
    # The CSRF middleware already checked header == cookie; here we bind the token to
    # this session so a cookie planted by another subdomain cannot be used.
    if request.method not in SAFE_METHODS and not auth.csrf_matches_session(
        session, request.headers.get(CSRF_HEADER)
    ):
        raise PermissionDeniedError("Invalid CSRF token. Refresh the page and try again.")
    principal = load_principal(db, user, session.id)
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def client_ip(request: Request) -> str | None:
    return valid_ip(request.client.host if request.client else None)
