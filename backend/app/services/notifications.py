"""Customer notifications (CLAUDE.md §3.10).

Flow: a workshop event calls `notify()` inside its own transaction. That writes a
Notification row (channel chosen, text rendered, single-use links redacted) and
schedules delivery for after the commit. Delivery runs in the Celery worker
(`app.workers.tasks.send_notification`), so the job workflow never waits on, or fails
because of, a provider.

Channel rules:
- WhatsApp only with the customer's current WhatsApp consent granted, a phone number,
  and an approved template name configured for the event.
- Email for service messages unless the customer withdrew email consent.
- The customer's preferred contact method decides which is tried first. With neither
  available the notification is logged as skipped, with the reason.

Retries: transient provider failures are retried by the worker with backoff; permanent
failures are marked failed with the provider's reason. Staff can retry failed messages,
except those that carried a single-use quotation link (send a new link instead).
"""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from string import Formatter
from typing import Any

from sqlalchemy import event, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.time import utcnow
from app.db.session import get_sessionmaker
from app.integrations.delivery import PermanentDeliveryError, TransientDeliveryError
from app.integrations.email import EmailSender, OutgoingEmail, get_email_sender
from app.integrations.whatsapp import (
    WhatsAppSender,
    WhatsAppTemplateMessage,
    get_whatsapp_sender,
)
from app.models import (
    Branch,
    Customer,
    CustomerConsent,
    CustomerContact,
    Notification,
    NotificationTemplate,
    Organisation,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.job_card import Ref
from app.schemas.notification import (
    NotificationRead,
    TemplateRead,
    TemplateUpdate,
)
from app.services import audit

logger = logging.getLogger(__name__)

LINK_MARKER = "[customer link]"
MAX_ATTEMPTS = 6

PLACEHOLDERS: dict[str, str] = {
    "customer_name": "Customer's name",
    "workshop_name": "Your workshop's name",
    "workshop_phone": "Branch phone number",
    "job_number": "Job card number",
    "vehicle": "Vehicle, e.g. N 123 W Toyota Hilux",
    "quote_number": "Quotation number",
    "total": "Quotation total",
    "valid_until": "Quotation valid until",
    "link": "Customer's quotation link (sent only, never stored)",
    "invoice_number": "Invoice number",
    "amount_due": "Amount due on the invoice",
    "due_date": "Invoice due date",
}


@dataclass(frozen=True)
class EventDefaults:
    label: str
    subject: str
    body: str
    whatsapp_params: tuple[str, ...]
    placeholders: tuple[str, ...]


_COMMON = ("customer_name", "workshop_name", "workshop_phone")

DEFAULTS: dict[str, EventDefaults] = {
    "vehicle_received": EventDefaults(
        label="Vehicle received",
        subject="We have received your vehicle {vehicle}",
        body=(
            "Hello {customer_name},\n\n"
            "{workshop_name} has received your vehicle {vehicle} (job {job_number}). "
            "We will be in touch once it has been inspected.\n\n"
            "{workshop_name} {workshop_phone}"
        ),
        whatsapp_params=("customer_name", "vehicle", "job_number", "workshop_name"),
        placeholders=(*_COMMON, "job_number", "vehicle"),
    ),
    "quotation_sent": EventDefaults(
        label="Quotation ready",
        subject="Quotation {quote_number} from {workshop_name}",
        body=(
            "Hello {customer_name},\n\n"
            "{workshop_name} has prepared quotation {quote_number} for your vehicle {vehicle}.\n"
            "Total: {total}\nValid until: {valid_until}\n\n"
            "Review and approve or decline it here:\n{link}\n\n"
            "Opening the link does not approve the work."
        ),
        whatsapp_params=("customer_name", "quote_number", "total", "link"),
        placeholders=(
            *_COMMON,
            "job_number",
            "vehicle",
            "quote_number",
            "total",
            "valid_until",
            "link",
        ),
    ),
    "ready_for_collection": EventDefaults(
        label="Ready for collection",
        subject="Your vehicle {vehicle} is ready for collection",
        body=(
            "Hello {customer_name},\n\n"
            "Your vehicle {vehicle} (job {job_number}) is ready for collection at "
            "{workshop_name}.\n\n{workshop_name} {workshop_phone}"
        ),
        whatsapp_params=("customer_name", "vehicle", "workshop_name"),
        placeholders=(*_COMMON, "job_number", "vehicle"),
    ),
    "invoice_issued": EventDefaults(
        label="Invoice issued",
        subject="Invoice {invoice_number} from {workshop_name}",
        body=(
            "Hello {customer_name},\n\n"
            "{workshop_name} has issued invoice {invoice_number} for job {job_number}.\n"
            "Amount due: {amount_due}\nDue date: {due_date}\n\n"
            "{workshop_name} {workshop_phone}"
        ),
        whatsapp_params=("customer_name", "invoice_number", "amount_due", "due_date"),
        placeholders=(
            *_COMMON,
            "job_number",
            "vehicle",
            "invoice_number",
            "amount_due",
            "due_date",
        ),
    ),
}


def vehicle_label(vehicle: Any) -> str:
    """'N 123 W Toyota Hilux' (registration or VIN, then make and model)."""
    ident = vehicle.registration_number or vehicle.vin or ""
    return " ".join(x for x in (ident, vehicle.make, vehicle.model) if x)


def money_label(amount: Any, currency: str) -> str:
    symbol = "N$" if currency == "NAD" else currency
    return f"{symbol} {amount:,.2f}"


# --------------------------------------------------------------------------- senders


@dataclass
class _Senders:
    """Indirection so tests can swap providers for the worker as well as the API."""

    email: Callable[[], EmailSender] = get_email_sender
    whatsapp: Callable[[], WhatsAppSender] = get_whatsapp_sender


senders = _Senders()


# --------------------------------------------------------------------------- templates


def check_placeholders(text: str, allowed: tuple[str, ...]) -> None:
    """Only plain {name} placeholders from the allowed list; no attribute access or format
    specs, so edited templates can never reach into Python objects."""
    for _, field_name, spec, conversion in Formatter().parse(text):
        if field_name is None:
            continue
        if spec or conversion or field_name not in allowed:
            raise ConflictError(
                f"Unknown placeholder {{{field_name}}}. Use one of: "
                + ", ".join(f"{{{p}}}" for p in allowed),
                details={"placeholder": field_name},
            )


def render(text: str, context: dict[str, str]) -> str:
    return text.format_map({k: context.get(k, "") for k in PLACEHOLDERS})


@dataclass(frozen=True)
class EffectiveTemplate:
    event: str
    is_enabled: bool
    email_subject: str
    email_body: str
    whatsapp_template_name: str | None
    whatsapp_language: str


def template_for(db: Session, organisation_id: uuid.UUID, event_name: str) -> EffectiveTemplate:
    d = DEFAULTS[event_name]
    row = db.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.organisation_id == organisation_id,
            NotificationTemplate.event == event_name,
        )
    )
    if row is None:
        return EffectiveTemplate(event_name, True, d.subject, d.body, None, "en")
    return EffectiveTemplate(
        event_name,
        row.is_enabled,
        row.email_subject,
        row.email_body,
        row.whatsapp_template_name,
        row.whatsapp_language,
    )


def _template_read(db: Session, organisation_id: uuid.UUID, event_name: str) -> TemplateRead:
    t = template_for(db, organisation_id, event_name)
    d = DEFAULTS[event_name]
    return TemplateRead(
        event=event_name,  # type: ignore[arg-type]
        label=d.label,
        is_enabled=t.is_enabled,
        email_subject=t.email_subject,
        email_body=t.email_body,
        whatsapp_template_name=t.whatsapp_template_name,
        whatsapp_language=t.whatsapp_language,
        whatsapp_params=list(d.whatsapp_params),
        placeholders={p: PLACEHOLDERS[p] for p in d.placeholders},
    )


def list_templates(db: Session, principal: Principal) -> list[TemplateRead]:
    principal.require_in_any_branch(P.NOTIFICATIONS_VIEW)
    return [_template_read(db, principal.organisation_id, e) for e in DEFAULTS]


def update_template(
    db: Session, principal: Principal, event_name: str, body: TemplateUpdate
) -> TemplateRead:
    principal.require(P.NOTIFICATIONS_MANAGE)
    allowed = DEFAULTS[event_name].placeholders
    check_placeholders(body.email_subject, allowed)
    check_placeholders(body.email_body, allowed)
    row = db.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.organisation_id == principal.organisation_id,
            NotificationTemplate.event == event_name,
        )
    )
    if row is None:
        row = NotificationTemplate(organisation_id=principal.organisation_id, event=event_name)
        db.add(row)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="notification_template.updated",
        entity_type="notification_template",
        entity_id=None,
        summary=f"Notification '{DEFAULTS[event_name].label}' "
        f"{'enabled' if body.is_enabled else 'turned off'} and template saved",
    )
    db.commit()
    return _template_read(db, principal.organisation_id, event_name)


# --------------------------------------------------------------------------- recipients

CALLING_CODES = {"NA": "264", "ZA": "27", "BW": "267", "ZM": "260", "AO": "244", "ZW": "263"}


def to_e164(phone: str, country_code: str) -> str | None:
    """'0812345678' in Namibia -> '264812345678'. Returns None if it cannot be resolved."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if phone.strip().startswith("+"):
        return digits if 8 <= len(digits) <= 15 else None
    if digits.startswith("00"):
        return digits[2:] if 8 <= len(digits) - 2 <= 15 else None
    code = CALLING_CODES.get(country_code)
    if code and digits.startswith("0"):
        return code + digits[1:]
    return None


def _current_consent(db: Session, customer_id: uuid.UUID, channel: str) -> str | None:
    return db.scalar(
        select(CustomerConsent.status)
        .where(CustomerConsent.customer_id == customer_id, CustomerConsent.channel == channel)
        .order_by(CustomerConsent.recorded_at.desc())
        .limit(1)
    )


def _primary(db: Session, customer_id: uuid.UUID, kind: str) -> str | None:
    return db.scalar(
        select(CustomerContact.value)
        .where(CustomerContact.customer_id == customer_id, CustomerContact.kind == kind)
        .order_by(CustomerContact.is_primary.desc(), CustomerContact.position)
        .limit(1)
    )


@dataclass(frozen=True)
class Route:
    channel: str  # email | whatsapp | none
    recipient: str | None
    skip_reason: str | None = None


def choose_route(
    db: Session, customer: Customer, country_code: str, template: EffectiveTemplate
) -> Route:
    reasons: list[str] = []
    options: dict[str, Route] = {}

    phone = _primary(db, customer.id, "phone")
    if _current_consent(db, customer.id, "whatsapp") != "granted":
        reasons.append("no WhatsApp consent")
    elif not phone:
        reasons.append("no phone number")
    elif not template.whatsapp_template_name:
        reasons.append("no approved WhatsApp template configured")
    elif (e164 := to_e164(phone, country_code)) is None:
        reasons.append("phone number could not be converted to international format")
    else:
        options["whatsapp"] = Route("whatsapp", e164)

    email = _primary(db, customer.id, "email")
    if not email:
        reasons.append("no email address")
    elif _current_consent(db, customer.id, "email") == "withdrawn":
        reasons.append("email consent withdrawn")
    else:
        options["email"] = Route("email", email)

    order = (
        ["email", "whatsapp"]
        if customer.preferred_contact_method == "email"
        else ["whatsapp", "email"]
    )
    for channel in order:
        if channel in options:
            return options[channel]
    return Route("none", None, "; ".join(reasons).capitalize() + ".")


# --------------------------------------------------------------------------- notify


def _enqueue_after_commit(db: Session, notification_id: uuid.UUID, link: str | None) -> None:
    pending: list[tuple[uuid.UUID, str | None]] = db.info.setdefault("pending_notifications", [])
    pending.append((notification_id, link))
    if db.info.get("notification_hook"):
        return
    db.info["notification_hook"] = True

    def after_commit(session: Session) -> None:
        items = session.info.pop("pending_notifications", [])
        session.info.pop("notification_hook", None)
        for nid, secret in items:
            enqueue(nid, secret)

    def after_rollback(session: Session) -> None:
        session.info.pop("pending_notifications", None)
        session.info.pop("notification_hook", None)

    event.listen(db, "after_commit", after_commit, once=True)
    event.listen(db, "after_soft_rollback", lambda s, _tx: after_rollback(s), once=True)


def enqueue(notification_id: uuid.UUID, link: str | None = None) -> None:
    """Hand the notification to the worker. Never raises: if the queue is unavailable the
    row stays queued and the periodic sweep picks it up."""
    try:
        if get_settings().celery_eager:
            deliver(notification_id, link, final_attempt=False)
            return
        from app.workers.tasks import send_notification

        send_notification.apply_async(args=[str(notification_id), link])
    except Exception:
        logger.exception("notification_enqueue_failed", extra={"id": str(notification_id)})


def notify(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    customer_id: uuid.UUID,
    event_name: str,
    context: dict[str, str],
    link: str | None = None,
    related_type: str | None = None,
    related_id: uuid.UUID | None = None,
    actor: Principal | None = None,
) -> Notification | None:
    """Record a notification in the caller's transaction and send it after commit."""
    template = template_for(db, organisation_id, event_name)
    if not template.is_enabled:
        return None
    org = db.get_one(Organisation, organisation_id)
    customer = db.get_one(Customer, customer_id)
    branch = db.get(Branch, branch_id) if branch_id else None
    ctx = {
        "customer_name": customer.display_name,
        "workshop_name": org.name,
        "workshop_phone": (branch.phone if branch and branch.phone else org.phone) or "",
        **context,
        "link": LINK_MARKER if link else "",
    }
    route = choose_route(db, customer, org.country_code, template)
    params = [ctx.get(p, "") for p in DEFAULTS[event_name].whatsapp_params]
    n = Notification(
        organisation_id=organisation_id,
        branch_id=branch_id,
        customer_id=customer_id,
        event=event_name,
        channel=route.channel,
        recipient=route.recipient,
        subject=render(template.email_subject, ctx) if route.channel == "email" else None,
        body=render(template.email_body, ctx),
        template_params=json.dumps(params) if route.channel == "whatsapp" else None,
        has_secret_link=bool(link),
        status="skipped" if route.channel == "none" else "queued",
        skip_reason=route.skip_reason,
        related_type=related_type,
        related_id=related_id,
        created_by_user_id=actor.user_id if actor else None,
    )
    db.add(n)
    db.flush()
    if n.status == "queued":
        _enqueue_after_commit(db, n.id, link)
    return n


# --------------------------------------------------------------------------- deliver


def deliver(notification_id: uuid.UUID | str, link: str | None, *, final_attempt: bool) -> None:
    """Send one notification (worker side, own session).

    Raises TransientDeliveryError when the worker should retry. On the final attempt a
    transient failure is recorded as failed instead.
    """
    with get_sessionmaker()() as db:
        n = db.scalar(
            select(Notification)
            .where(Notification.id == uuid.UUID(str(notification_id)))
            .with_for_update(skip_locked=True)
        )
        if n is None or n.status != "queued":
            return
        n.attempts += 1
        if n.has_secret_link and not link:
            _fail(
                n, "The customer link is no longer available. Send a new link from the quotation."
            )
            db.commit()
            return
        try:
            if n.channel == "email":
                sender = senders.email()
                sender.deliver(
                    OutgoingEmail(
                        to=n.recipient or "",
                        subject=n.subject or "",
                        text=n.body.replace(LINK_MARKER, link or ""),
                    )
                )
                n.provider = "smtp"
            elif n.channel == "whatsapp":
                tmpl = template_for(db, n.organisation_id, n.event)
                if not tmpl.whatsapp_template_name:
                    raise PermanentDeliveryError("No approved WhatsApp template is configured.")
                params = [
                    p.replace(LINK_MARKER, link or "")
                    for p in json.loads(n.template_params or "[]")
                ]
                wa = senders.whatsapp()
                n.provider_message_id = wa.send(
                    WhatsAppTemplateMessage(
                        to=n.recipient or "",
                        template_name=tmpl.whatsapp_template_name,
                        language=tmpl.whatsapp_language,
                        params=params,
                    )
                )
                n.provider = wa.name
            n.status, n.sent_at, n.last_error = "sent", utcnow(), None
            db.commit()
        except PermanentDeliveryError as exc:
            _fail(n, str(exc))
            db.commit()
        except TransientDeliveryError as exc:
            n.last_error = str(exc)[:500]
            if final_attempt or n.attempts >= MAX_ATTEMPTS:
                _fail(n, f"Gave up after {n.attempts} attempts: {exc}")
                db.commit()
                return
            db.commit()
            raise


def _fail(n: Notification, reason: str) -> None:
    n.status, n.failed_at, n.last_error = "failed", utcnow(), reason[:500]


def requeue_stale(older_than: timedelta = timedelta(minutes=3)) -> int:
    """Periodic sweep: re-enqueue notifications stuck in 'queued' (e.g. Redis was down)."""
    with get_sessionmaker()() as db:
        ids = list(
            db.scalars(
                select(Notification.id).where(
                    Notification.status == "queued",
                    Notification.has_secret_link.is_(False),
                    Notification.updated_at < utcnow() - older_than,
                )
            )
        )
    for nid in ids:
        enqueue(nid)
    return len(ids)


# --------------------------------------------------------------------------- provider webhook


STATUS_ORDER = {"sent": 1, "delivered": 2, "read": 3}


def apply_whatsapp_status(db: Session, payload: dict[str, Any]) -> int:
    """Apply Meta delivery status callbacks. Returns how many notifications changed."""
    changed = 0
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            for st in (change.get("value") or {}).get("statuses", []) or []:
                provider_id, status = st.get("id"), st.get("status")
                if not provider_id or status not in ("sent", "delivered", "read", "failed"):
                    continue
                n = db.scalar(
                    select(Notification)
                    .where(
                        Notification.provider_message_id == str(provider_id),
                        Notification.channel == "whatsapp",
                    )
                    .with_for_update()
                )
                if n is None:
                    continue
                if status == "failed":
                    errors = st.get("errors") or [{}]
                    _fail(n, str(errors[0].get("title") or "Delivery failed (provider)."))
                elif STATUS_ORDER.get(status, 0) > STATUS_ORDER.get(n.status, 0):
                    n.status = status
                    if status == "delivered":
                        n.delivered_at = utcnow()
                else:
                    continue
                changed += 1
    db.commit()
    return changed


# --------------------------------------------------------------------------- staff API


def _visible_branches(principal: Principal) -> set[uuid.UUID] | None:
    branches = principal.branch_ids_with(P.NOTIFICATIONS_VIEW)
    if branches is not None and not branches:
        raise PermissionDeniedError("You do not have permission to view notifications.")
    return branches


def _read(n: Notification, customer_name: str) -> NotificationRead:
    return NotificationRead(
        id=n.id,
        event=n.event,  # type: ignore[arg-type]
        event_label=DEFAULTS[n.event].label,
        channel=n.channel,  # type: ignore[arg-type]
        recipient=n.recipient,
        subject=n.subject,
        body=n.body,
        status=n.status,  # type: ignore[arg-type]
        skip_reason=n.skip_reason,
        attempts=n.attempts,
        last_error=n.last_error,
        provider=n.provider,
        customer=Ref(id=n.customer_id, name=customer_name),
        related_type=n.related_type,
        related_id=n.related_id,
        created_at=n.created_at,
        sent_at=n.sent_at,
        delivered_at=n.delivered_at,
        failed_at=n.failed_at,
        can_retry=n.status == "failed" and not n.has_secret_link,
    )


def list_notifications(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    status: str | None = None,
    event_name: str | None = None,
    customer_id: uuid.UUID | None = None,
    related_id: uuid.UUID | None = None,
) -> tuple[list[NotificationRead], int]:
    branches = _visible_branches(principal)
    conditions: list[Any] = [Notification.organisation_id == principal.organisation_id]
    if branches is not None:
        conditions.append(
            or_(Notification.branch_id.in_(branches), Notification.branch_id.is_(None))
        )
    if status:
        conditions.append(Notification.status == status)
    if event_name:
        conditions.append(Notification.event == event_name)
    if customer_id:
        conditions.append(Notification.customer_id == customer_id)
    if related_id:
        conditions.append(Notification.related_id == related_id)
    total = db.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0
    rows = db.execute(
        select(Notification, Customer.display_name)
        .join(Customer, Customer.id == Notification.customer_id)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .limit(params.page_size)
        .offset(params.offset)
    ).all()
    return [_read(n, name) for n, name in rows], total


def retry(db: Session, principal: Principal, notification_id: uuid.UUID) -> NotificationRead:
    n = db.scalar(
        select(Notification)
        .where(
            Notification.id == notification_id,
            Notification.organisation_id == principal.organisation_id,
        )
        .with_for_update()
    )
    if n is None or (n.branch_id and not principal.can(P.NOTIFICATIONS_VIEW, n.branch_id)):
        raise NotFoundError("Notification not found.")
    principal.require_in_any_branch(P.NOTIFICATIONS_VIEW)
    if n.status != "failed":
        raise ConflictError("Only failed notifications can be retried.")
    if n.has_secret_link:
        raise ConflictError(
            "This message carried a single-use link. Send a new link from the quotation."
        )
    n.status, n.failed_at, n.attempts = "queued", None, 0
    audit.record(
        db,
        organisation_id=n.organisation_id,
        branch_id=n.branch_id,
        actor=principal,
        action="notification.retried",
        entity_type="notification",
        entity_id=n.id,
        summary=f"Retried '{DEFAULTS[n.event].label}' notification to {n.recipient}",
    )
    _enqueue_after_commit(db, n.id, None)
    db.commit()
    db.refresh(n)
    name = db.scalar(select(Customer.display_name).where(Customer.id == n.customer_id)) or ""
    return _read(n, name)
