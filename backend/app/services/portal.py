"""Customer self-service portal (CLAUDE.md §3.11).

Security model:
- Portal accounts are separate from staff users. A portal session (cookie
  `wp_portal_session`) authorises only /api/v1/portal endpoints.
- Sign-in is by single-use email link (15 minutes); only token hashes are stored. Link
  requests never reveal whether an account exists.
- Every query is filtered by the signed-in account's organisation and customer. Records
  of other customers are "not found", never "forbidden", so their existence is not
  confirmed. IDs from the browser are never trusted on their own.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import client_ip_var
from app.core.errors import ConflictError, NotAuthenticatedError, NotFoundError
from app.core.security import hash_token, new_token
from app.core.time import utcnow
from app.integrations.email import OutgoingEmail
from app.models import (
    Customer,
    CustomerConsent,
    CustomerContact,
    Inspection,
    Invoice,
    JobCard,
    JobStatusHistory,
    Organisation,
    OrganisationSettings,
    Payment,
    PaymentAllocation,
    PortalAccount,
    PortalSession,
    PortalToken,
    Quotation,
    QuotationDecision,
    QuotationItem,
    QuotationVersion,
    Vehicle,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.customer import normalise_phone
from app.schemas.portal import (
    PortalAccess,
    PortalDecision,
    PortalDocumentRef,
    PortalHome,
    PortalInvoice,
    PortalJob,
    PortalJobDetail,
    PortalMe,
    PortalMeUpdate,
    PortalQuotation,
    PortalStatusStep,
    PortalVehicle,
)
from app.schemas.quotation import ItemRead
from app.services import audit, invoices, notifications, quotations
from app.services.job_workflow import LABELS, TERMINAL, JobStatus
from app.services.lines import ITEM_COLUMNS

LINK_MINUTES = 15
SESSION_DAYS = 30
IDLE_HOURS = 24 * 7
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class PortalPrincipal:
    account: PortalAccount
    session: PortalSession

    @property
    def organisation_id(self) -> uuid.UUID:
        return self.account.organisation_id

    @property
    def customer_id(self) -> uuid.UUID:
        return self.account.customer_id


def read_only_principal(organisation_id: uuid.UUID) -> Principal:
    """A staff-shaped principal with no permissions, for reusing read models after the
    portal has already scoped the record to the customer. It can never pass a permission
    check."""
    return Principal(
        user_id=uuid.UUID(int=0),
        organisation_id=organisation_id,
        email="",
        full_name="Customer",
        session_id=None,
    )


# --------------------------------------------------------------------------- staff: access


def _customer_for_staff(db: Session, principal: Principal, customer_id: uuid.UUID) -> Customer:
    principal.require_in_any_branch(P.CUSTOMERS_VIEW)
    c = db.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.organisation_id == principal.organisation_id
        )
    )
    if c is None:
        raise NotFoundError("Customer not found.")
    return c


def _access(account: PortalAccount | None) -> PortalAccess:
    return PortalAccess(
        enabled=bool(account and account.is_active),
        email=account.email if account else None,
        invited_at=account.invited_at if account else None,
        last_sign_in_at=account.last_sign_in_at if account else None,
    )


def get_access(db: Session, principal: Principal, customer_id: uuid.UUID) -> PortalAccess:
    c = _customer_for_staff(db, principal, customer_id)
    return _access(db.scalar(select(PortalAccount).where(PortalAccount.customer_id == c.id)))


def _sign_in_email(
    db: Session, settings: Settings, account: PortalAccount, *, invited: bool
) -> OutgoingEmail:
    token = new_token()
    db.add(
        PortalToken(
            account_id=account.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(minutes=LINK_MINUTES),
        )
    )
    org = db.get_one(Organisation, account.organisation_id)
    customer = db.get_one(Customer, account.customer_id)
    url = f"{settings.app_base_url}/portal/auth#token={token}"
    intro = (
        f"{org.name} has given you access to its customer portal, where you can follow "
        "your vehicle's repairs, approve quotations and see invoices."
        if invited
        else f"Use this link to sign in to the {org.name} customer portal."
    )
    return OutgoingEmail(
        to=account.email,
        subject=f"Sign in to {org.name}",
        text=(
            f"Hello {customer.display_name},\n\n{intro}\n\n{url}\n\n"
            f"The link works once and expires in {LINK_MINUTES} minutes. If you did not "
            "expect this email, you can ignore it."
        ),
    )


def invite(
    db: Session, principal: Principal, settings: Settings, customer_id: uuid.UUID, email: str
) -> tuple[PortalAccess, OutgoingEmail]:
    c = _customer_for_staff(db, principal, customer_id)
    principal.require_in_any_branch(P.CUSTOMERS_MANAGE)
    on_file = set(
        db.scalars(
            select(CustomerContact.value).where(
                CustomerContact.customer_id == c.id, CustomerContact.kind == "email"
            )
        )
    )
    if email.lower() not in {e.lower() for e in on_file}:
        raise ConflictError("Use one of the customer's email addresses on file.")
    taken = db.scalar(
        select(PortalAccount).where(
            PortalAccount.organisation_id == c.organisation_id,
            PortalAccount.email == email,
            PortalAccount.customer_id != c.id,
        )
    )
    if taken:
        raise ConflictError("Another customer already uses this email for the portal.")
    account = db.scalar(select(PortalAccount).where(PortalAccount.customer_id == c.id))
    if account is None:
        account = PortalAccount(
            organisation_id=c.organisation_id,
            customer_id=c.id,
            email=email,
            created_by_user_id=principal.user_id,
        )
        db.add(account)
    account.email, account.is_active, account.invited_at = email, True, utcnow()
    db.flush()
    message = _sign_in_email(db, settings, account, invited=True)
    audit.record(
        db,
        organisation_id=c.organisation_id,
        actor=principal,
        action="portal.invited",
        entity_type="customer",
        entity_id=c.id,
        summary=f"Customer portal access sent to {email}",
    )
    db.commit()
    return _access(account), message


def disable(db: Session, principal: Principal, customer_id: uuid.UUID) -> PortalAccess:
    c = _customer_for_staff(db, principal, customer_id)
    principal.require_in_any_branch(P.CUSTOMERS_MANAGE)
    account = db.scalar(select(PortalAccount).where(PortalAccount.customer_id == c.id))
    if account is None or not account.is_active:
        raise ConflictError("Portal access is not enabled for this customer.")
    account.is_active = False
    db.execute(
        update(PortalSession)
        .where(PortalSession.account_id == account.id, PortalSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    audit.record(
        db,
        organisation_id=c.organisation_id,
        actor=principal,
        action="portal.disabled",
        entity_type="customer",
        entity_id=c.id,
        summary=f"Customer portal access removed for {account.email}",
    )
    db.commit()
    return _access(account)


# --------------------------------------------------------------------------- customer: auth


def request_link(db: Session, settings: Settings, email: str) -> list[OutgoingEmail]:
    """Emails a sign-in link to every active account with this address. The caller always
    responds the same way, whether or not an account exists."""
    accounts = list(
        db.scalars(
            select(PortalAccount).where(PortalAccount.email == email, PortalAccount.is_active)
        )
    )
    messages = [_sign_in_email(db, settings, a, invited=False) for a in accounts]
    db.commit()
    return messages


def consume(db: Session, token: str, existing_csrf: str | None = None) -> tuple[str, str]:
    """Exchange a sign-in link for a session. Returns (session token, csrf token).

    An existing CSRF cookie value is reused so a staff session in the same browser keeps
    working (both bind to the same double-submit cookie)."""
    row = db.scalar(
        select(PortalToken).where(PortalToken.token_hash == hash_token(token)).with_for_update()
    )
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise NotAuthenticatedError(
            "This sign-in link is invalid or has expired. Request a new one."
        )
    account = db.get_one(PortalAccount, row.account_id)
    if not account.is_active:
        raise NotAuthenticatedError(
            "This sign-in link is invalid or has expired. Request a new one."
        )
    row.used_at = now
    session_token = new_token()
    csrf = existing_csrf if existing_csrf and 20 <= len(existing_csrf) <= 100 else new_token()
    db.add(
        PortalSession(
            organisation_id=account.organisation_id,
            account_id=account.id,
            token_hash=hash_token(session_token),
            csrf_token=csrf,
            last_seen_at=now,
            expires_at=now + timedelta(days=SESSION_DAYS),
            ip_address=client_ip_var.get(),
        )
    )
    account.last_sign_in_at = now
    audit.record(
        db,
        organisation_id=account.organisation_id,
        actor_type="customer",
        action="portal.signed_in",
        entity_type="customer",
        entity_id=account.customer_id,
        summary=f"Customer signed in to the portal ({account.email})",
    )
    db.commit()
    return session_token, csrf


def resolve(db: Session, token: str) -> PortalPrincipal:
    now = utcnow()
    row = db.execute(
        select(PortalSession, PortalAccount)
        .join(PortalAccount, PortalAccount.id == PortalSession.account_id)
        .where(PortalSession.token_hash == hash_token(token))
    ).one_or_none()
    if row is None:
        raise NotAuthenticatedError("Please sign in.")
    session, account = row
    if (
        session.revoked_at is not None
        or session.expires_at <= now
        or session.last_seen_at + timedelta(hours=IDLE_HOURS) <= now
        or not account.is_active
    ):
        raise NotAuthenticatedError("Your session has ended. Please sign in again.")
    if now - session.last_seen_at > timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return PortalPrincipal(account=account, session=session)


def logout(db: Session, who: PortalPrincipal) -> None:
    db.execute(
        update(PortalSession).where(PortalSession.id == who.session.id).values(revoked_at=utcnow())
    )
    db.commit()


# --------------------------------------------------------------------------- customer: reads


def _consent(db: Session, customer_id: uuid.UUID, channel: str) -> str | None:
    return db.scalar(
        select(CustomerConsent.status)
        .where(CustomerConsent.customer_id == customer_id, CustomerConsent.channel == channel)
        .order_by(CustomerConsent.recorded_at.desc())
        .limit(1)
    )


def _phone(db: Session, customer_id: uuid.UUID) -> CustomerContact | None:
    return db.scalar(
        select(CustomerContact)
        .where(CustomerContact.customer_id == customer_id, CustomerContact.kind == "phone")
        .order_by(CustomerContact.is_primary.desc(), CustomerContact.position)
        .limit(1)
    )


def me(db: Session, who: PortalPrincipal) -> PortalMe:
    customer = db.get_one(Customer, who.customer_id)
    org = db.get_one(Organisation, who.organisation_id)
    phone = _phone(db, customer.id)
    settings = db.get_one(OrganisationSettings, who.organisation_id)
    return PortalMe(
        customer_name=customer.display_name,
        email=who.account.email,
        organisation_name=org.name,
        organisation_phone=org.phone,
        organisation_email=org.email,
        phone=phone.value if phone else None,
        preferred_contact_method=customer.preferred_contact_method,  # type: ignore[arg-type]
        whatsapp_consent=_consent(db, customer.id, "whatsapp") == "granted",
        email_consent=_consent(db, customer.id, "email") != "withdrawn",
        timezone=settings.timezone,
        date_format=settings.date_format,
    )


def update_me(db: Session, who: PortalPrincipal, body: PortalMeUpdate) -> PortalMe:
    customer = db.get_one(Customer, who.customer_id)
    changes = body.model_dump(exclude_unset=True)
    summary = []
    if "phone" in changes:
        if not body.phone:
            raise ConflictError("Enter a phone number.")
        try:
            value = normalise_phone(body.phone)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        contact = _phone(db, customer.id)
        if contact is None:
            db.add(
                CustomerContact(
                    organisation_id=customer.organisation_id,
                    customer_id=customer.id,
                    kind="phone",
                    value=value,
                    is_primary=True,
                )
            )
        else:
            contact.value = value
        summary.append("phone number")
    if body.preferred_contact_method is not None:
        customer.preferred_contact_method = body.preferred_contact_method
        summary.append("preferred contact method")
    for channel, granted in (("whatsapp", body.whatsapp_consent), ("email", body.email_consent)):
        if granted is None:
            continue
        current = _consent(db, customer.id, channel)
        new = "granted" if granted else "withdrawn"
        if current == new or (channel == "email" and current is None and granted):
            continue
        db.add(
            CustomerConsent(
                organisation_id=customer.organisation_id,
                customer_id=customer.id,
                channel=channel,
                status=new,
                method="customer_portal",
                evidence=f"Changed in the customer portal by {who.account.email}",
            )
        )
        summary.append(f"{channel} consent {new}")
    if summary:
        audit.record(
            db,
            organisation_id=customer.organisation_id,
            actor_type="customer",
            action="portal.profile_updated",
            entity_type="customer",
            entity_id=customer.id,
            summary=f"Customer updated in the portal: {', '.join(summary)}",
        )
    db.commit()
    return me(db, who)


def vehicles(db: Session, who: PortalPrincipal) -> list[PortalVehicle]:
    rows = db.scalars(
        select(Vehicle)
        .where(
            Vehicle.organisation_id == who.organisation_id,
            Vehicle.customer_id == who.customer_id,
            Vehicle.archived_at.is_(None),
        )
        .order_by(Vehicle.make, Vehicle.model)
    )
    return [
        PortalVehicle(
            id=v.id,
            label=notifications.vehicle_label(v),
            registration_number=v.registration_number,
            vin=v.vin,
            make=v.make,
            model=v.model,
            year=v.year,
            odometer_km=v.odometer_km,
        )
        for v in rows
    ]


def _job_item(job: JobCard, vehicle: Vehicle) -> PortalJob:
    return PortalJob(
        id=job.id,
        job_number=job.job_number,
        vehicle=notifications.vehicle_label(vehicle),
        status=job.status,
        status_label=LABELS[JobStatus(job.status)],
        received_at=job.received_at,
        promised_at=job.promised_at,
        collected_at=job.collected_at,
        complaint=job.complaint,
    )


def jobs(db: Session, who: PortalPrincipal) -> list[PortalJob]:
    rows = db.execute(
        select(JobCard, Vehicle)
        .join(Vehicle, Vehicle.id == JobCard.vehicle_id)
        .where(
            JobCard.organisation_id == who.organisation_id, JobCard.customer_id == who.customer_id
        )
        .order_by(JobCard.received_at.desc())
        .limit(100)
    ).all()
    return [_job_item(j, v) for j, v in rows]


def _own_job(db: Session, who: PortalPrincipal, job_id: uuid.UUID) -> JobCard:
    job = db.scalar(
        select(JobCard).where(
            JobCard.id == job_id,
            JobCard.organisation_id == who.organisation_id,
            JobCard.customer_id == who.customer_id,
        )
    )
    if job is None:
        raise NotFoundError("Job not found.")
    return job


def _visible_version(db: Session, q: Quotation) -> QuotationVersion | None:
    v = quotations.current_version(db, q.id)
    return None if v.status == "draft" else v


def job_detail(db: Session, who: PortalPrincipal, job_id: uuid.UUID) -> PortalJobDetail:
    job = _own_job(db, who, job_id)
    vehicle = db.get_one(Vehicle, job.vehicle_id)
    history = db.execute(
        select(JobStatusHistory.to_status, JobStatusHistory.changed_at)
        .where(JobStatusHistory.job_card_id == job.id)
        .order_by(JobStatusHistory.changed_at)
    ).all()
    today = invoices.today(db, job.organisation_id)
    quote_ref = None
    q = db.scalar(select(Quotation).where(Quotation.job_card_id == job.id))
    if q and (v := _visible_version(db, q)):
        quote_ref = PortalDocumentRef(
            id=q.id,
            number=q.quote_number,
            status=quotations.effective_status(v, today),
            total=v.total,
            date=v.sent_at,
        )
    invs = db.scalars(
        select(Invoice)
        .where(Invoice.job_card_id == job.id, Invoice.status == "issued")
        .order_by(Invoice.issue_date)
    )
    insp = db.scalars(
        select(Inspection)
        .where(Inspection.job_card_id == job.id, Inspection.status == "submitted")
        .order_by(Inspection.submitted_at)
    )
    done = JobStatus(job.status) in TERMINAL
    return PortalJobDetail(
        **_job_item(job, vehicle).model_dump(),
        work_performed=job.work_performed if done else None,
        history=[PortalStatusStep(label=LABELS[JobStatus(s)], at=at) for s, at in history],
        quotation=quote_ref,
        invoices=[
            PortalDocumentRef(
                id=i.id,
                number=i.invoice_number or "",
                status=invoices.payment_status(i),
                total=i.total,
                balance_due=invoices.balance_due(i),
                date=i.issue_date,
            )
            for i in invs
        ],
        inspections=[
            PortalDocumentRef(
                id=i.id,
                number={"intake": "Vehicle inspection", "quality": "Quality inspection"}.get(
                    i.kind, "Inspection"
                ),
                status=i.status,
                date=i.submitted_at,
            )
            for i in insp
        ],
    )


def _own_quotation(db: Session, who: PortalPrincipal, quotation_id: uuid.UUID) -> Quotation:
    q = db.scalar(
        select(Quotation).where(
            Quotation.id == quotation_id,
            Quotation.organisation_id == who.organisation_id,
            Quotation.customer_id == who.customer_id,
        )
    )
    if q is None or _visible_version(db, q) is None:
        raise NotFoundError("Quotation not found.")
    return q


def quotation(db: Session, who: PortalPrincipal, quotation_id: uuid.UUID) -> PortalQuotation:
    q = _own_quotation(db, who, quotation_id)
    v = quotations.current_version(db, q.id)
    job = db.get_one(JobCard, q.job_card_id)
    status = quotations.effective_status(v, invoices.today(db, q.organisation_id))
    decision = db.scalar(select(QuotationDecision).where(QuotationDecision.version_id == v.id))
    items = db.scalars(
        select(QuotationItem)
        .where(QuotationItem.version_id == v.id)
        .order_by(QuotationItem.position)
    )
    return PortalQuotation(
        id=q.id,
        quote_number=q.quote_number,
        version_number=v.version_number,
        status=status,  # type: ignore[arg-type]
        job_number=job.job_number,
        vehicle=notifications.vehicle_label(db.get_one(Vehicle, job.vehicle_id)),
        currency_code=v.currency_code,
        prices_include_tax=v.prices_include_tax,
        valid_until=v.valid_until,
        items=[
            ItemRead.model_validate({"id": i.id, **{c: getattr(i, c) for c in ITEM_COLUMNS}})
            for i in items
        ],
        subtotal=v.subtotal,
        tax_total=v.tax_total,
        total=v.total,
        notes=v.notes,
        terms=v.terms,
        decision=decision.decision if decision else None,  # type: ignore[arg-type]
        decided_at=decision.decided_at if decision else None,
        can_decide=status == "sent" and JobStatus(job.status) not in TERMINAL,
    )


def decide(
    db: Session, who: PortalPrincipal, quotation_id: uuid.UUID, body: PortalDecision
) -> PortalQuotation:
    q = _own_quotation(db, who, quotation_id)
    v = quotations.current_version(db, q.id, lock=True)
    job = db.get_one(JobCard, q.job_card_id)
    status = quotations.effective_status(v, invoices.today(db, q.organisation_id))
    if status != "sent" or JobStatus(job.status) in TERMINAL:
        raise ConflictError("This quotation can no longer be approved or declined online.")
    if body.decision == "approved" and not body.accept_terms:
        raise ConflictError("Confirm that you accept the quotation and its terms.")
    customer = db.get_one(Customer, who.customer_id)
    quotations._decide(
        db,
        v,
        decision=body.decision,
        method="customer_portal",
        customer_name=customer.display_name,
        evidence=f"Signed in to the customer portal as {who.account.email}",
        comments=body.comments,
        recorded_by=None,
    )
    audit.record(
        db,
        organisation_id=q.organisation_id,
        branch_id=q.branch_id,
        actor_type="customer",
        action=f"quotation.{body.decision}",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Quotation {q.quote_number} v{v.version_number} {body.decision} in the "
        f"customer portal for {v.currency_code} {v.total}",
    )
    db.commit()
    return quotation(db, who, quotation_id)


def invoice_list(db: Session, who: PortalPrincipal) -> list[PortalInvoice]:
    today = invoices.today(db, who.organisation_id)
    rows = db.execute(
        select(Invoice, JobCard.job_number)
        .outerjoin(JobCard, JobCard.id == Invoice.job_card_id)
        .where(
            Invoice.organisation_id == who.organisation_id,
            Invoice.customer_id == who.customer_id,
            Invoice.status == "issued",
        )
        .order_by(Invoice.issue_date.desc())
    ).all()
    receipts: dict[uuid.UUID, list[PortalDocumentRef]] = {}
    for inv_id, p in db.execute(
        select(PaymentAllocation.invoice_id, Payment)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.invoice_id.in_([i.id for i, _ in rows]))
        .order_by(Payment.received_at)
    ):
        receipts.setdefault(inv_id, []).append(
            PortalDocumentRef(
                id=p.id, number=p.receipt_number, status=p.kind, total=p.amount, date=p.received_at
            )
        )
    return [
        PortalInvoice(
            id=i.id,
            invoice_number=i.invoice_number or "",
            job_number=job_number,
            issue_date=i.issue_date,  # type: ignore[arg-type]
            due_date=i.due_date,
            currency_code=i.currency_code,
            total=i.total,
            balance_due=invoices.balance_due(i),
            payment_status=invoices.payment_status(i),
            is_overdue=invoices.is_overdue(i, today),
            receipts=receipts.get(i.id, []),
        )
        for i, job_number in rows
    ]


def home(db: Session, who: PortalPrincipal) -> PortalHome:
    all_jobs = jobs(db, who)
    open_jobs = [j for j in all_jobs if JobStatus(j.status) not in TERMINAL]
    today = invoices.today(db, who.organisation_id)
    to_review = []
    for q in db.scalars(
        select(Quotation).where(
            Quotation.organisation_id == who.organisation_id,
            Quotation.customer_id == who.customer_id,
        )
    ):
        v = quotations.current_version(db, q.id)
        if quotations.effective_status(v, today) == "sent":
            to_review.append(
                PortalDocumentRef(
                    id=q.id, number=q.quote_number, status="sent", total=v.total, date=v.sent_at
                )
            )
    owed = sum((max(i.balance_due, ZERO) for i in invoice_list(db, who)), ZERO)
    currency = db.scalar(
        select(OrganisationSettings.currency_code).where(
            OrganisationSettings.organisation_id == who.organisation_id
        )
    )
    return PortalHome(
        me=me(db, who),
        vehicles=vehicles(db, who),
        open_jobs=open_jobs,
        quotations_to_review=to_review,
        outstanding=owed,
        currency_code=currency or "NAD",
    )


# --------------------------------------------------------------------------- documents


def owns_invoice(db: Session, who: PortalPrincipal, invoice_id: uuid.UUID) -> Invoice:
    inv = db.scalar(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.organisation_id == who.organisation_id,
            Invoice.customer_id == who.customer_id,
            Invoice.status == "issued",
        )
    )
    if inv is None:
        raise NotFoundError("Invoice not found.")
    return inv


def owns_payment(db: Session, who: PortalPrincipal, payment_id: uuid.UUID) -> Payment:
    p = db.scalar(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.organisation_id == who.organisation_id,
            Payment.customer_id == who.customer_id,
        )
    )
    if p is None:
        raise NotFoundError("Receipt not found.")
    return p


def owns_inspection(
    db: Session, who: PortalPrincipal, inspection_id: uuid.UUID
) -> tuple[Inspection, JobCard]:
    row = db.execute(
        select(Inspection, JobCard)
        .join(JobCard, JobCard.id == Inspection.job_card_id)
        .where(
            Inspection.id == inspection_id,
            Inspection.status == "submitted",
            JobCard.organisation_id == who.organisation_id,
            JobCard.customer_id == who.customer_id,
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Inspection not found.")
    return row[0], row[1]


def owns_quotation(db: Session, who: PortalPrincipal, quotation_id: uuid.UUID) -> Quotation:
    return _own_quotation(db, who, quotation_id)
