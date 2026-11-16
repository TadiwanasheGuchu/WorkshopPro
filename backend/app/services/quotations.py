"""Quotations: versions, line items, sending, customer decisions (CLAUDE.md §3.6).

- Only draft versions can change. Sending locks the version.
- Revising a sent/approved/rejected version creates a new draft and supersedes the old
  one, so a changed quotation always needs a new approval.
- A decision always records the exact version and total.
- Opening the public link never approves anything.
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import client_ip_var, user_agent_var
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_token, new_token
from app.core.time import utcnow
from app.integrations.email import OutgoingEmail
from app.models import (
    Branch,
    Customer,
    CustomerContact,
    JobCard,
    Organisation,
    OrganisationSettings,
    Quotation,
    QuotationDecision,
    QuotationItem,
    QuotationLink,
    QuotationVersion,
    User,
    Vehicle,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.job_card import Ref, VehicleRef
from app.schemas.quotation import (
    DecisionRead,
    DraftUpdate,
    ItemRead,
    LinkRead,
    PublicDecision,
    PublicItem,
    PublicQuotation,
    QuotationCapabilities,
    QuotationListItem,
    QuotationRead,
    ReviseRequest,
    SendResult,
    StaffDecision,
    VersionRead,
    VersionSummary,
)
from app.services import audit, numbering
from app.services.job_cards import get_visible_job_card
from app.services.job_workflow import TERMINAL, JobStatus
from app.services.lines import ITEM_COLUMNS, price_lines

LIVE = ("draft", "sent", "approved", "rejected")


class InvalidLinkError(AppError):
    status_code = 404
    code = "invalid_link"


def _settings(db: Session, organisation_id: uuid.UUID) -> OrganisationSettings:
    return db.get_one(OrganisationSettings, organisation_id)


def _today(db: Session, organisation_id: uuid.UUID) -> date:
    return utcnow().astimezone(ZoneInfo(_settings(db, organisation_id).timezone)).date()


def effective_status(version: QuotationVersion, today: date) -> str:
    if version.status == "sent" and version.valid_until and version.valid_until < today:
        return "expired"
    return version.status


def current_version(
    db: Session, quotation_id: uuid.UUID, *, lock: bool = False
) -> QuotationVersion:
    stmt = select(QuotationVersion).where(
        QuotationVersion.quotation_id == quotation_id, QuotationVersion.status.in_(LIVE)
    )
    if lock:
        stmt = stmt.with_for_update()
    version = db.scalar(stmt)
    if version is None:  # pragma: no cover - a quotation always has one live version
        raise NotFoundError("Quotation has no current version.")
    return version


# --------------------------------------------------------------------------- access


def _load(
    db: Session, principal: Principal, quotation_id: uuid.UUID, permission: str
) -> tuple[Quotation, JobCard]:
    q = db.scalar(
        select(Quotation).where(
            Quotation.id == quotation_id, Quotation.organisation_id == principal.organisation_id
        )
    )
    if q is None or not principal.can(P.QUOTATIONS_VIEW, q.branch_id):
        raise NotFoundError("Quotation not found.")
    principal.require(permission, q.branch_id)
    job = db.get_one(JobCard, q.job_card_id)
    return q, job


# --------------------------------------------------------------------------- reads


def _names(db: Session, ids: list[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all())


def _version_read(db: Session, v: QuotationVersion, today: date) -> VersionRead:
    items = db.scalars(
        select(QuotationItem)
        .where(QuotationItem.version_id == v.id)
        .order_by(QuotationItem.position)
    )
    decision = db.scalar(select(QuotationDecision).where(QuotationDecision.version_id == v.id))
    link = db.scalar(
        select(QuotationLink)
        .where(QuotationLink.version_id == v.id)
        .order_by(QuotationLink.created_at.desc())
        .limit(1)
    )
    names = _names(db, [v.sent_by_user_id, decision.recorded_by_user_id if decision else None])
    return VersionRead(
        id=v.id,
        version_number=v.version_number,
        status=effective_status(v, today),  # type: ignore[arg-type]
        currency_code=v.currency_code,
        prices_include_tax=v.prices_include_tax,
        valid_until=v.valid_until,
        terms=v.terms,
        notes=v.notes,
        subtotal=v.subtotal,
        tax_total=v.tax_total,
        total=v.total,
        sent_at=v.sent_at,
        sent_by=names.get(v.sent_by_user_id) if v.sent_by_user_id else None,
        created_at=v.created_at,
        revision_reason=v.revision_reason,
        items=[
            ItemRead(
                id=i.id,
                kind=i.kind,  # type: ignore[arg-type]
                description=i.description,
                part_number=i.part_number,
                quantity=i.quantity,
                unit_price=i.unit_price,
                tax_rate_id=i.tax_rate_id,
                tax_rate_name=i.tax_rate_name,
                tax_rate_percent=i.tax_rate_percent,
                line_subtotal=i.line_subtotal,
                line_tax=i.line_tax,
                line_total=i.line_total,
            )
            for i in items
        ],
        decision=DecisionRead(
            decision=decision.decision,  # type: ignore[arg-type]
            method=decision.method,
            total=decision.total,
            currency_code=decision.currency_code,
            customer_name=decision.customer_name,
            evidence=decision.evidence,
            comments=decision.comments,
            recorded_by=names.get(decision.recorded_by_user_id)
            if decision.recorded_by_user_id
            else None,
            decided_at=decision.decided_at,
        )
        if decision
        else None,
        link=LinkRead(
            expires_at=link.expires_at,
            first_viewed_at=link.first_viewed_at,
            last_viewed_at=link.last_viewed_at,
            view_count=link.view_count,
            used_at=link.used_at,
            revoked_at=link.revoked_at,
        )
        if link
        else None,
    )


def _vehicle_ref(v: Vehicle) -> VehicleRef:
    return VehicleRef(
        id=v.id,
        registration_number=v.registration_number,
        vin=v.vin,
        make=v.make,
        model=v.model,
        year=v.year,
    )


def _primary_email(db: Session, customer_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(CustomerContact.value).where(
            CustomerContact.customer_id == customer_id,
            CustomerContact.kind == "email",
            CustomerContact.is_primary,
        )
    )


def read(db: Session, principal: Principal, q: Quotation, job: JobCard) -> QuotationRead:
    today = _today(db, q.organisation_id)
    current = current_version(db, q.id)
    versions = list(
        db.scalars(
            select(QuotationVersion)
            .where(QuotationVersion.quotation_id == q.id)
            .order_by(QuotationVersion.version_number.desc())
        )
    )
    status = effective_status(current, today)
    manage = principal.can(P.QUOTATIONS_MANAGE, q.branch_id)
    job_open = JobStatus(job.status) not in TERMINAL
    return QuotationRead(
        id=q.id,
        quote_number=q.quote_number,
        branch=Ref(
            id=q.branch_id,
            name=db.scalar(select(Branch.name).where(Branch.id == q.branch_id)) or "",
        ),
        job_card=Ref(id=job.id, name=job.job_number),
        customer=Ref(
            id=q.customer_id,
            name=db.scalar(select(Customer.display_name).where(Customer.id == q.customer_id)) or "",
        ),
        customer_email=_primary_email(db, q.customer_id),
        vehicle=_vehicle_ref(db.get_one(Vehicle, job.vehicle_id)),
        current=_version_read(db, current, today),
        versions=[
            VersionSummary(
                id=v.id,
                version_number=v.version_number,
                status=effective_status(v, today),  # type: ignore[arg-type]
                total=v.total,
                sent_at=v.sent_at,
            )
            for v in versions
        ],
        capabilities=QuotationCapabilities(
            edit=manage and job_open and status == "draft",
            send=manage and job_open and status == "draft",
            revise=manage and job_open and status in ("sent", "approved", "rejected", "expired"),
            record_decision=job_open
            and status == "sent"
            and principal.can(P.QUOTATIONS_RECORD_DECISION, q.branch_id),
        ),
    )


def get_quotation(db: Session, principal: Principal, quotation_id: uuid.UUID) -> QuotationRead:
    q, job = _load(db, principal, quotation_id, P.QUOTATIONS_VIEW)
    return read(db, principal, q, job)


def for_job(db: Session, principal: Principal, job_id: uuid.UUID) -> QuotationRead | None:
    job = get_visible_job_card(db, principal, job_id)
    if not principal.can(P.QUOTATIONS_VIEW, job.branch_id):
        return None
    q = db.scalar(select(Quotation).where(Quotation.job_card_id == job.id))
    return read(db, principal, q, job) if q else None


def list_quotations(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    status: str | None = None,
    search: str | None = None,
) -> tuple[list[QuotationListItem], int]:
    branches = principal.branch_ids_with(P.QUOTATIONS_VIEW)
    if branches is not None and not branches:
        raise PermissionDeniedError("You do not have permission to view quotations.")
    today = _today(db, principal.organisation_id)
    conditions: list[Any] = [
        Quotation.organisation_id == principal.organisation_id,
        QuotationVersion.status.in_(LIVE),
    ]
    if branches is not None:
        conditions.append(Quotation.branch_id.in_(branches))
    if status == "expired":
        conditions += [QuotationVersion.status == "sent", QuotationVersion.valid_until < today]
    elif status == "sent":
        conditions += [
            QuotationVersion.status == "sent",
            (QuotationVersion.valid_until.is_(None)) | (QuotationVersion.valid_until >= today),
        ]
    elif status:
        conditions.append(QuotationVersion.status == status)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(
            Quotation.quote_number.ilike(term)
            | Quotation.customer_id.in_(
                select(Customer.id).where(Customer.display_name.ilike(term))
            )
        )
    base = (
        select(Quotation, QuotationVersion, JobCard, Customer.display_name, Vehicle)
        .join(QuotationVersion, QuotationVersion.quotation_id == Quotation.id)
        .join(JobCard, JobCard.id == Quotation.job_card_id)
        .join(Customer, Customer.id == Quotation.customer_id)
        .join(Vehicle, Vehicle.id == JobCard.vehicle_id)
        .where(*conditions)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(QuotationVersion.updated_at.desc())
        .limit(params.page_size)
        .offset(params.offset)
    ).all()
    return [
        QuotationListItem(
            id=q.id,
            quote_number=q.quote_number,
            version_number=v.version_number,
            status=effective_status(v, today),  # type: ignore[arg-type]
            total=v.total,
            currency_code=v.currency_code,
            customer=Ref(id=q.customer_id, name=name),
            vehicle=_vehicle_ref(vehicle),
            job_card=Ref(id=job.id, name=job.job_number),
            updated_at=v.updated_at,
        )
        for q, v, job, name, vehicle in rows
    ], total


# --------------------------------------------------------------------------- writes


def _new_version(
    db: Session, q: Quotation, number: int, principal: Principal, reason: str | None = None
) -> QuotationVersion:
    s = _settings(db, q.organisation_id)
    v = QuotationVersion(
        organisation_id=q.organisation_id,
        quotation_id=q.id,
        version_number=number,
        status="draft",
        currency_code=s.currency_code,
        prices_include_tax=s.prices_include_tax,
        terms=s.quotation_terms,
        created_by_user_id=principal.user_id,
        revision_reason=reason,
    )
    db.add(v)
    db.flush()
    return v


def create_for_job(db: Session, principal: Principal, job_id: uuid.UUID) -> QuotationRead:
    job = get_visible_job_card(db, principal, job_id, lock=True)
    principal.require(P.QUOTATIONS_MANAGE, job.branch_id)
    if JobStatus(job.status) in TERMINAL:
        raise ConflictError("This job is closed.")
    if db.scalar(select(Quotation.id).where(Quotation.job_card_id == job.id)):
        raise ConflictError("This job already has a quotation. Revise it instead.")
    q = Quotation(
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        job_card_id=job.id,
        customer_id=job.customer_id,
        quote_number=numbering.allocate(
            db, principal.organisation_id, numbering.DocumentType.QUOTATION
        ),
        created_by_user_id=principal.user_id,
    )
    db.add(q)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("This job already has a quotation.") from exc
    _new_version(db, q, 1, principal)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="quotation.created",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Quotation {q.quote_number} started for job {job.job_number}",
    )
    db.commit()
    return read(db, principal, q, job)


def save_draft(
    db: Session, principal: Principal, quotation_id: uuid.UUID, body: DraftUpdate
) -> QuotationRead:
    q, job = _load(db, principal, quotation_id, P.QUOTATIONS_MANAGE)
    v = current_version(db, q.id, lock=True)
    if v.status != "draft":
        raise ConflictError("Sent quotations cannot be edited. Create a revision instead.")
    priced, totals = price_lines(
        db, q.organisation_id, body.items, prices_include_tax=v.prices_include_tax
    )
    db.query(QuotationItem).filter(QuotationItem.version_id == v.id).delete()
    db.add_all(QuotationItem(version_id=v.id, **p.fields) for p in priced)
    v.subtotal, v.tax_total, v.total = totals.subtotal, totals.tax, totals.total
    v.valid_until, v.terms, v.notes = body.valid_until, body.terms, body.notes
    db.commit()
    return read(db, principal, q, job)


def _issue_link(db: Session, settings: Settings, v: QuotationVersion, tz: ZoneInfo) -> str:
    db.execute(
        update(QuotationLink)
        .where(QuotationLink.version_id == v.id, QuotationLink.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    token = new_token()
    if v.valid_until:
        expires = datetime.combine(v.valid_until + timedelta(days=1), time.min, tzinfo=tz)
    else:
        expires = utcnow() + timedelta(days=30)
    db.add(
        QuotationLink(
            organisation_id=v.organisation_id,
            version_id=v.id,
            token_hash=hash_token(token),
            expires_at=expires,
        )
    )
    return f"{settings.app_base_url}/quote#token={token}"


def send(
    db: Session,
    principal: Principal,
    settings: Settings,
    quotation_id: uuid.UUID,
    email_customer: bool,
) -> tuple[SendResult, OutgoingEmail | None]:
    q, job = _load(db, principal, quotation_id, P.QUOTATIONS_MANAGE)
    if JobStatus(job.status) in TERMINAL:
        raise ConflictError("This job is closed.")
    v = current_version(db, q.id, lock=True)
    if v.status != "draft":
        raise ConflictError("Only a draft can be sent. To send again, create a new customer link.")
    if not db.scalar(
        select(func.count()).select_from(QuotationItem).where(QuotationItem.version_id == v.id)
    ):
        raise ConflictError("Add at least one line before sending.")
    org_settings = _settings(db, q.organisation_id)
    tz = ZoneInfo(org_settings.timezone)
    today = _today(db, q.organisation_id)
    if v.valid_until is None:
        v.valid_until = today + timedelta(days=org_settings.quotation_validity_days)
    elif v.valid_until < today:
        raise ConflictError("The 'valid until' date is in the past.")
    v.status, v.sent_at, v.sent_by_user_id = "sent", utcnow(), principal.user_id
    url = _issue_link(db, settings, v, tz)
    recipient = _primary_email(db, q.customer_id) if email_customer else None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=q.branch_id,
        actor=principal,
        action="quotation.sent",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Quotation {q.quote_number} v{v.version_number} sent "
        f"({v.currency_code} {v.total}){' by email' if recipient else ''}",
        changes={"quotation_id": q.id, "version": v.version_number, "total": v.total},
    )
    db.commit()
    email = None
    if recipient:
        org = db.get_one(Organisation, q.organisation_id)
        customer = db.get_one(Customer, q.customer_id)
        email = OutgoingEmail(
            to=recipient,
            subject=f"Quotation {q.quote_number} from {org.name}",
            text=(
                f"Hello {customer.display_name},\n\n"
                f"{org.name} has prepared quotation {q.quote_number} for job {job.job_number}.\n"
                f"Total: {v.currency_code} {v.total:,.2f}\n"
                f"Valid until: {v.valid_until:%d/%m/%Y}\n\n"
                f"Review and approve or decline it here:\n{url}\n\n"
                "Opening the link does not approve the work.\n"
            ),
        )
    return SendResult(
        quotation=read(db, principal, q, job), approval_url=url, emailed_to=recipient
    ), email


def new_link(db: Session, principal: Principal, settings: Settings, quotation_id: uuid.UUID) -> str:
    q, _ = _load(db, principal, quotation_id, P.QUOTATIONS_MANAGE)
    v = current_version(db, q.id, lock=True)
    if effective_status(v, _today(db, q.organisation_id)) != "sent":
        raise ConflictError("Links can only be created for a sent, unexpired quotation.")
    url = _issue_link(db, settings, v, ZoneInfo(_settings(db, q.organisation_id).timezone))
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=q.branch_id,
        actor=principal,
        action="quotation.link_reissued",
        entity_type="quotation",
        entity_id=q.id,
        summary=f"New customer link for quotation {q.quote_number}; previous links revoked",
    )
    db.commit()
    return url


def revise(
    db: Session, principal: Principal, quotation_id: uuid.UUID, body: ReviseRequest
) -> QuotationRead:
    q, job = _load(db, principal, quotation_id, P.QUOTATIONS_MANAGE)
    if JobStatus(job.status) in TERMINAL:
        raise ConflictError("This job is closed.")
    old = current_version(db, q.id, lock=True)
    if old.status == "draft":
        raise ConflictError("The current version is still a draft; edit it directly.")
    was_approved = old.status == "approved"
    old.status = "superseded"
    db.execute(
        update(QuotationLink)
        .where(QuotationLink.version_id == old.id, QuotationLink.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.flush()
    new = _new_version(db, q, old.version_number + 1, principal, body.reason)
    new.prices_include_tax, new.currency_code = old.prices_include_tax, old.currency_code
    new.terms, new.notes = old.terms, old.notes
    for item in db.scalars(select(QuotationItem).where(QuotationItem.version_id == old.id)):
        db.add(
            QuotationItem(
                version_id=new.id,
                **{c: getattr(item, c) for c in ITEM_COLUMNS},
            )
        )
    new.subtotal, new.tax_total, new.total = old.subtotal, old.tax_total, old.total
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=q.branch_id,
        actor=principal,
        action="quotation.revised",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Quotation {q.quote_number} revised to v{new.version_number}"
        f"{' (previous approval no longer applies)' if was_approved else ''}: {body.reason}",
        changes={"quotation_id": q.id, "superseded_version": old.version_number},
    )
    db.commit()
    return read(db, principal, q, job)


def _decide(
    db: Session,
    v: QuotationVersion,
    *,
    decision: str,
    method: str,
    customer_name: str,
    evidence: str | None,
    comments: str | None,
    recorded_by: uuid.UUID | None,
) -> None:
    db.add(
        QuotationDecision(
            organisation_id=v.organisation_id,
            version_id=v.id,
            decision=decision,
            method=method,
            total=v.total,
            currency_code=v.currency_code,
            customer_name=customer_name,
            evidence=evidence,
            comments=comments,
            recorded_by_user_id=recorded_by,
            ip_address=client_ip_var.get(),
            user_agent=user_agent_var.get(),
        )
    )
    v.status = decision
    db.execute(
        update(QuotationLink)
        .where(QuotationLink.version_id == v.id, QuotationLink.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def record_decision(
    db: Session, principal: Principal, quotation_id: uuid.UUID, body: StaffDecision
) -> QuotationRead:
    q, job = _load(db, principal, quotation_id, P.QUOTATIONS_RECORD_DECISION)
    v = current_version(db, q.id, lock=True)
    status = effective_status(v, _today(db, q.organisation_id))
    if status == "expired":
        raise ConflictError("This quotation has expired. Revise it and send the new version.")
    if status != "sent":
        raise ConflictError("Only a sent quotation can be approved or rejected.")
    _decide(
        db,
        v,
        decision=body.decision,
        method=body.method,
        customer_name=body.customer_name,
        evidence=body.evidence,
        comments=body.comments,
        recorded_by=principal.user_id,
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=q.branch_id,
        actor=principal,
        action=f"quotation.{body.decision}",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Quotation {q.quote_number} v{v.version_number} {body.decision} by "
        f"{body.customer_name} ({body.method}) for {v.currency_code} {v.total}",
        changes={
            "quotation_id": q.id,
            "version": v.version_number,
            "total": v.total,
            "evidence": body.evidence,
        },
    )
    db.commit()
    return read(db, principal, q, job)


# --------------------------------------------------------------------------- public link


def _link(db: Session, token: str, *, lock: bool = False) -> tuple[QuotationLink, QuotationVersion]:
    stmt = select(QuotationLink).where(QuotationLink.token_hash == hash_token(token))
    if lock:
        stmt = stmt.with_for_update()
    link = db.scalar(stmt)
    if (
        link is None
        or (link.revoked_at is not None and link.used_at is None)
        or link.expires_at <= utcnow()
    ):
        raise InvalidLinkError(
            "This link is invalid or has expired. Ask the workshop for a new one."
        )
    return link, db.get_one(QuotationVersion, link.version_id)


def _public(db: Session, link: QuotationLink, v: QuotationVersion) -> PublicQuotation:
    q = db.get_one(Quotation, v.quotation_id)
    org = db.get_one(Organisation, q.organisation_id)
    job = db.get_one(JobCard, q.job_card_id)
    vehicle = db.get_one(Vehicle, job.vehicle_id)
    customer = db.get_one(Customer, q.customer_id)
    branch = db.get_one(Branch, q.branch_id)
    decision = db.scalar(select(QuotationDecision).where(QuotationDecision.version_id == v.id))
    status = effective_status(v, _today(db, q.organisation_id))
    items = db.scalars(
        select(QuotationItem)
        .where(QuotationItem.version_id == v.id)
        .order_by(QuotationItem.position)
    )
    return PublicQuotation(
        organisation_name=org.name,
        organisation_phone=branch.phone or org.phone,
        organisation_email=branch.email or org.email,
        branch_name=branch.name,
        quote_number=q.quote_number,
        version_number=v.version_number,
        status=status,  # type: ignore[arg-type]
        customer_name=customer.display_name,
        vehicle=" ".join(
            x
            for x in (vehicle.registration_number or vehicle.vin, vehicle.make, vehicle.model)
            if x
        ),
        currency_code=v.currency_code,
        prices_include_tax=v.prices_include_tax,
        items=[
            PublicItem(
                kind=i.kind,  # type: ignore[arg-type]
                description=i.description,
                quantity=i.quantity,
                unit_price=i.unit_price,
                tax_rate_percent=i.tax_rate_percent,
                line_total=i.line_total,
            )
            for i in items
        ],
        subtotal=v.subtotal,
        tax_total=v.tax_total,
        total=v.total,
        valid_until=v.valid_until,
        terms=v.terms,
        notes=v.notes,
        can_decide=status == "sent" and link.used_at is None and link.revoked_at is None,
        decision=decision.decision if decision else None,  # type: ignore[arg-type]
        decided_at=decision.decided_at if decision else None,
    )


def public_view(db: Session, token: str) -> PublicQuotation:
    """Records that the customer opened the link. Viewing is never approval."""
    link, v = _link(db, token, lock=True)
    now = utcnow()
    link.first_viewed_at = link.first_viewed_at or now
    link.last_viewed_at = now
    link.view_count += 1
    db.commit()
    return _public(db, link, v)


def public_decide(db: Session, token: str, body: PublicDecision) -> PublicQuotation:
    link, v = _link(db, token, lock=True)
    if link.used_at is not None or link.revoked_at is not None:
        raise ConflictError("A decision has already been recorded for this quotation.")
    q = db.get_one(Quotation, v.quotation_id)
    status = effective_status(v, _today(db, q.organisation_id))
    if status != "sent":
        raise ConflictError(
            "This quotation can no longer be approved online. Please contact the workshop."
        )
    _decide(
        db,
        v,
        decision=body.decision,
        method="customer_link",
        customer_name=body.customer_name,
        evidence="Decision submitted through the customer quotation link",
        comments=body.comments,
        recorded_by=None,
    )
    link.used_at = utcnow()
    job = db.get_one(JobCard, q.job_card_id)
    audit.record(
        db,
        organisation_id=q.organisation_id,
        branch_id=q.branch_id,
        actor_type="customer",
        action=f"quotation.{body.decision}",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Quotation {q.quote_number} v{v.version_number} {body.decision} online by "
        f"{body.customer_name} for {v.currency_code} {v.total}",
        changes={"quotation_id": q.id, "version": v.version_number, "total": v.total},
    )
    db.commit()
    return _public(db, link, v)


# --------------------------------------------------------------------------- documents


def version_for_token(db: Session, token: str) -> QuotationVersion:
    """The version a customer link points at, validated like viewing (no view recorded)."""
    return _link(db, token)[1]


def read_for_document(db: Session, v: QuotationVersion) -> QuotationRead:
    """A read model of one specific version, for the customer's PDF. Carries no staff
    capabilities or version history."""
    q = db.get_one(Quotation, v.quotation_id)
    job = db.get_one(JobCard, q.job_card_id)
    today = _today(db, q.organisation_id)
    return QuotationRead(
        id=q.id,
        quote_number=q.quote_number,
        branch=Ref(
            id=q.branch_id,
            name=db.scalar(select(Branch.name).where(Branch.id == q.branch_id)) or "",
        ),
        job_card=Ref(id=job.id, name=job.job_number),
        customer=Ref(
            id=q.customer_id,
            name=db.scalar(select(Customer.display_name).where(Customer.id == q.customer_id)) or "",
        ),
        customer_email=None,
        vehicle=_vehicle_ref(db.get_one(Vehicle, job.vehicle_id)),
        current=_version_read(db, v, today),
        versions=[],
        capabilities=QuotationCapabilities(
            edit=False, send=False, revise=False, record_decision=False
        ),
    )
