import hashlib
import hmac
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import AppSettings, CurrentPrincipal, DbSession, Paging
from app.core.errors import NotFoundError, PermissionDeniedError
from app.schemas.common import Page
from app.schemas.notification import Event, NotificationRead, Status, TemplateRead, TemplateUpdate
from app.services import notifications

router = APIRouter(tags=["notifications"])


@router.get(
    "/notifications",
    response_model=Page[NotificationRead],
    summary="Customer notification log",
    description="Newest first. Single-use links are never stored; the body shows a placeholder.",
)
def list_notifications(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    status: Status | None = None,
    event: Event | None = None,
    customer_id: uuid.UUID | None = None,
    related_id: uuid.UUID | None = None,
) -> Page[NotificationRead]:
    items, total = notifications.list_notifications(
        db,
        principal,
        paging,
        status=status,
        event_name=event,
        customer_id=customer_id,
        related_id=related_id,
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/notifications/{notification_id}/retry",
    response_model=NotificationRead,
    summary="Retry a failed notification",
)
def retry(
    notification_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> NotificationRead:
    return notifications.retry(db, principal, notification_id)


@router.get(
    "/notification-templates",
    response_model=list[TemplateRead],
    summary="Notification events and their templates",
)
def list_templates(principal: CurrentPrincipal, db: DbSession) -> list[TemplateRead]:
    return notifications.list_templates(db, principal)


@router.put(
    "/notification-templates/{event}",
    response_model=TemplateRead,
    summary="Turn a notification on or off and edit its wording",
    description="Only the listed placeholders may be used. WhatsApp needs the name of a "
    "template approved by Meta; its body parameters are sent in the listed order.",
)
def update_template(
    event: Event, body: TemplateUpdate, principal: CurrentPrincipal, db: DbSession
) -> TemplateRead:
    return notifications.update_template(db, principal, event, body)


# --------------------------------------------------------------------------- webhook


@router.get(
    "/webhooks/whatsapp",
    response_class=PlainTextResponse,
    summary="WhatsApp webhook verification (Meta)",
)
def verify_webhook(
    settings: AppSettings,
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge", max_length=200)] = None,
) -> str:
    expected = settings.whatsapp_webhook_verify_token
    if not expected or mode != "subscribe" or not token or not hmac.compare_digest(token, expected):
        raise PermissionDeniedError("Webhook verification failed.")
    return challenge or ""


@router.post(
    "/webhooks/whatsapp",
    summary="WhatsApp delivery status callbacks (Meta)",
    description="Signed with the app secret (X-Hub-Signature-256). Disabled until "
    "WHATSAPP_APP_SECRET is set.",
)
async def whatsapp_webhook(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, int]:
    secret = settings.whatsapp_app_secret
    if not secret:
        raise NotFoundError("Not found.")
    raw = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise PermissionDeniedError("Invalid signature.")
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise PermissionDeniedError("Invalid payload.") from exc
    return {"updated": notifications.apply_whatsapp_status(db, payload)}
