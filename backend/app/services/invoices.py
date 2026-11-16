"""Invoices and credit notes (CLAUDE.md §3.9).

- A draft has no number and can change freely. Issuing allocates the number, fixes the
  dates and makes the invoice immutable (also enforced by a database trigger).
- Corrections after issue are credit notes; they never edit the invoice.
- amount_paid / amount_credited change only inside the transaction that records the
  payment allocation or credit note, with the invoice row locked.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.time import utcnow
from app.models import (
    Branch,
    CreditNote,
    CreditNoteItem,
    Customer,
    Invoice,
    InvoiceItem,
    JobCard,
    OrganisationSettings,
    Payment,
    PaymentAllocation,
    Quotation,
    QuotationItem,
    QuotationVersion,
    User,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.invoice import (
    CreditNoteCreate,
    CreditNoteRead,
    InvoiceCapabilities,
    InvoiceDraftUpdate,
    InvoiceListItem,
    InvoicePaymentLine,
    InvoiceRead,
)
from app.schemas.job_card import Ref
from app.schemas.quotation import ItemRead
from app.services import audit, numbering
from app.services.job_cards import get_visible_job_card
from app.services.job_workflow import JobStatus
from app.services.lines import ITEM_COLUMNS, price_lines

ZERO = Decimal("0.00")
CREDIT_ITEM_COLUMNS = (
    "description",
    "quantity",
    "unit_price",
    "tax_rate_name",
    "tax_rate_percent",
    "line_subtotal",
    "line_tax",
    "line_total",
)

# Work must have reached quality inspection before it can be invoiced.
INVOICEABLE = frozenset(
    {JobStatus.QUALITY_INSPECTION, JobStatus.READY_FOR_COLLECTION, JobStatus.COMPLETED}
)


def org_settings(db: Session, organisation_id: uuid.UUID) -> OrganisationSettings:
    return db.get_one(OrganisationSettings, organisation_id)


def today(db: Session, organisation_id: uuid.UUID) -> date:
    tz = ZoneInfo(org_settings(db, organisation_id).timezone)
    return utcnow().astimezone(tz).date()


# --------------------------------------------------------------------------- balances


def balance_due(inv: Invoice) -> Decimal:
    """Owed on an issued invoice. Negative means the customer has overpaid."""
    if inv.status != "issued":
        return ZERO
    return inv.total - inv.amount_credited - inv.amount_paid


def payment_status(inv: Invoice) -> str:
    if inv.status == "draft":
        return "draft"
    balance = balance_due(inv)
    if balance < 0:
        return "overpaid"
    if balance == 0:
        if inv.amount_paid == 0 and inv.amount_credited > 0:
            return "credited"
        return "paid"
    return "partially_paid" if inv.amount_paid > 0 else "unpaid"


def is_overdue(inv: Invoice, on: date) -> bool:
    return (
        inv.status == "issued"
        and balance_due(inv) > 0
        and inv.due_date is not None
        and inv.due_date < on
    )


# --------------------------------------------------------------------------- access


def load(
    db: Session,
    principal: Principal,
    invoice_id: uuid.UUID,
    permission: str = P.INVOICES_VIEW,
    *,
    lock: bool = False,
) -> Invoice:
    stmt = select(Invoice).where(
        Invoice.id == invoice_id, Invoice.organisation_id == principal.organisation_id
    )
    if lock:
        stmt = stmt.with_for_update()
    inv = db.scalar(stmt)
    if inv is None or not principal.can(P.INVOICES_VIEW, inv.branch_id):
        raise NotFoundError("Invoice not found.")
    principal.require(permission, inv.branch_id)
    return inv


# --------------------------------------------------------------------------- reads


def _names(db: Session, ids: list[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all())


def _list_item(
    inv: Invoice, customer_name: str, job_number: str | None, on: date
) -> InvoiceListItem:
    return InvoiceListItem(
        id=inv.id,
        invoice_number=inv.invoice_number,
        status=inv.status,  # type: ignore[arg-type]
        payment_status=payment_status(inv),  # type: ignore[arg-type]
        customer=Ref(id=inv.customer_id, name=customer_name),
        job_card=Ref(id=inv.job_card_id, name=job_number or "") if inv.job_card_id else None,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        is_overdue=is_overdue(inv, on),
        currency_code=inv.currency_code,
        total=inv.total,
        balance_due=balance_due(inv),
    )


def read(db: Session, principal: Principal, inv: Invoice) -> InvoiceRead:
    on = today(db, inv.organisation_id)
    customer_name = db.scalar(select(Customer.display_name).where(Customer.id == inv.customer_id))
    job_number = (
        db.scalar(select(JobCard.job_number).where(JobCard.id == inv.job_card_id))
        if inv.job_card_id
        else None
    )
    items = db.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == inv.id).order_by(InvoiceItem.position)
    )
    credit_notes = list(
        db.scalars(
            select(CreditNote)
            .where(CreditNote.invoice_id == inv.id)
            .order_by(CreditNote.created_at)
        )
    )
    payment_rows = db.execute(
        select(PaymentAllocation.amount, Payment)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.invoice_id == inv.id)
        .order_by(PaymentAllocation.created_at)
    ).all()
    names = _names(db, [inv.issued_by_user_id, *(c.created_by_user_id for c in credit_notes)])
    base = _list_item(inv, customer_name or "", job_number, on)

    manage = principal.can(P.INVOICES_MANAGE, inv.branch_id)
    issued = inv.status == "issued"
    balance = balance_due(inv)
    return InvoiceRead(
        **base.model_dump(),
        branch=Ref(
            id=inv.branch_id,
            name=db.scalar(select(Branch.name).where(Branch.id == inv.branch_id)) or "",
        ),
        prices_include_tax=inv.prices_include_tax,
        items=[
            ItemRead.model_validate({"id": i.id, **{c: getattr(i, c) for c in ITEM_COLUMNS}})
            for i in items
        ],
        subtotal=inv.subtotal,
        tax_total=inv.tax_total,
        amount_paid=inv.amount_paid,
        amount_credited=inv.amount_credited,
        notes=inv.notes,
        terms=inv.terms,
        issued_at=inv.issued_at,
        issued_by=names.get(inv.issued_by_user_id) if inv.issued_by_user_id else None,
        quotation_version_id=inv.quotation_version_id,
        credit_notes=[
            CreditNoteRead(
                id=c.id,
                credit_note_number=c.credit_note_number,
                issue_date=c.issue_date,
                reason=c.reason,
                subtotal=c.subtotal,
                tax_total=c.tax_total,
                total=c.total,
                created_by=names.get(c.created_by_user_id, ""),
            )
            for c in credit_notes
        ],
        payments=[
            InvoicePaymentLine(
                payment_id=p.id,
                receipt_number=p.receipt_number,
                kind=p.kind,  # type: ignore[arg-type]
                method=p.method,  # type: ignore[arg-type]
                received_at=p.received_at,
                amount=amount,
            )
            for amount, p in payment_rows
        ],
        capabilities=InvoiceCapabilities(
            edit=manage and not issued,
            issue=manage and not issued,
            delete=manage and not issued,
            credit=issued
            and inv.amount_credited < inv.total
            and principal.can(P.INVOICES_CREDIT, inv.branch_id),
            record_payment=issued
            and balance > 0
            and principal.can(P.PAYMENTS_RECORD, inv.branch_id),
            refund=issued and balance < 0 and principal.can(P.PAYMENTS_REFUND, inv.branch_id),
        ),
    )


def get_invoice(db: Session, principal: Principal, invoice_id: uuid.UUID) -> InvoiceRead:
    return read(db, principal, load(db, principal, invoice_id))


def for_job(db: Session, principal: Principal, job_id: uuid.UUID) -> list[InvoiceListItem]:
    job = get_visible_job_card(db, principal, job_id)
    if not principal.can(P.INVOICES_VIEW, job.branch_id):
        return []
    on = today(db, job.organisation_id)
    rows = db.execute(
        select(Invoice, Customer.display_name)
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(Invoice.job_card_id == job.id)
        .order_by(Invoice.created_at)
    ).all()
    return [_list_item(inv, name, job.job_number, on) for inv, name in rows]


def visible_branches(principal: Principal) -> set[uuid.UUID] | None:
    branches = principal.branch_ids_with(P.INVOICES_VIEW)
    if branches is not None and not branches:
        raise PermissionDeniedError("You do not have permission to view invoices.")
    return branches


def list_invoices(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[InvoiceListItem], int]:
    branches = visible_branches(principal)
    on = today(db, principal.organisation_id)
    balance = Invoice.total - Invoice.amount_credited - Invoice.amount_paid
    conditions: list[Any] = [Invoice.organisation_id == principal.organisation_id]
    if branches is not None:
        conditions.append(Invoice.branch_id.in_(branches))
    if customer_id:
        conditions.append(Invoice.customer_id == customer_id)
    if status == "draft":
        conditions.append(Invoice.status == "draft")
    elif status == "outstanding":
        conditions += [Invoice.status == "issued", balance > 0]
    elif status == "overdue":
        conditions += [Invoice.status == "issued", balance > 0, Invoice.due_date < on]
    elif status == "paid":
        conditions += [Invoice.status == "issued", balance <= 0]
    elif status == "issued":
        conditions.append(Invoice.status == "issued")
    if search:
        term = f"%{search.strip()}%"
        conditions.append(
            Invoice.invoice_number.ilike(term)
            | Invoice.customer_id.in_(select(Customer.id).where(Customer.display_name.ilike(term)))
            | Invoice.job_card_id.in_(select(JobCard.id).where(JobCard.job_number.ilike(term)))
        )
    base = (
        select(Invoice, Customer.display_name, JobCard.job_number)
        .join(Customer, Customer.id == Invoice.customer_id)
        .outerjoin(JobCard, JobCard.id == Invoice.job_card_id)
        .where(*conditions)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(Invoice.status, Invoice.issue_date.desc().nulls_first(), Invoice.created_at)
        .limit(params.page_size)
        .offset(params.offset)
    ).all()
    return [_list_item(inv, name, number, on) for inv, name, number in rows], total


# --------------------------------------------------------------------------- drafts


def create_for_job(db: Session, principal: Principal, job_id: uuid.UUID) -> InvoiceRead:
    """Start a draft for the job, prefilled from the approved quotation when there is one
    and nothing has been invoiced yet."""
    job = get_visible_job_card(db, principal, job_id, lock=True)
    principal.require(P.INVOICES_MANAGE, job.branch_id)
    if job.status == JobStatus.CANCELLED:
        raise ConflictError("This job was cancelled.")
    existing = list(db.scalars(select(Invoice).where(Invoice.job_card_id == job.id)))
    if any(i.status == "draft" for i in existing):
        raise ConflictError("This job already has a draft invoice.")

    s = org_settings(db, job.organisation_id)
    approved = None
    if not existing:
        approved = db.scalar(
            select(QuotationVersion)
            .join(Quotation, Quotation.id == QuotationVersion.quotation_id)
            .where(Quotation.job_card_id == job.id, QuotationVersion.status == "approved")
        )
    inv = Invoice(
        organisation_id=job.organisation_id,
        branch_id=job.branch_id,
        customer_id=job.customer_id,
        job_card_id=job.id,
        quotation_version_id=approved.id if approved else None,
        status="draft",
        currency_code=approved.currency_code if approved else s.currency_code,
        prices_include_tax=approved.prices_include_tax if approved else s.prices_include_tax,
        terms=s.invoice_terms,
        created_by_user_id=principal.user_id,
    )
    db.add(inv)
    db.flush()
    if approved:
        for item in db.scalars(
            select(QuotationItem)
            .where(QuotationItem.version_id == approved.id)
            .order_by(QuotationItem.position)
        ):
            db.add(InvoiceItem(invoice_id=inv.id, **{c: getattr(item, c) for c in ITEM_COLUMNS}))
        inv.subtotal, inv.tax_total, inv.total = (
            approved.subtotal,
            approved.tax_total,
            approved.total,
        )
    audit.record(
        db,
        organisation_id=inv.organisation_id,
        branch_id=inv.branch_id,
        actor=principal,
        action="invoice.draft_created",
        entity_type="invoice",
        entity_id=inv.id,
        summary=f"Draft invoice started for job {job.job_number}"
        + (" from the approved quotation" if approved else ""),
    )
    db.commit()
    return read(db, principal, inv)


def _require_draft(inv: Invoice) -> None:
    if inv.status != "draft":
        raise ConflictError("Issued invoices cannot be changed. Use a credit note.")


def save_draft(
    db: Session, principal: Principal, invoice_id: uuid.UUID, body: InvoiceDraftUpdate
) -> InvoiceRead:
    inv = load(db, principal, invoice_id, P.INVOICES_MANAGE, lock=True)
    _require_draft(inv)
    priced, totals = price_lines(
        db, inv.organisation_id, body.items, prices_include_tax=inv.prices_include_tax
    )
    db.query(InvoiceItem).filter(InvoiceItem.invoice_id == inv.id).delete()
    db.add_all(InvoiceItem(invoice_id=inv.id, **p.fields) for p in priced)
    inv.subtotal, inv.tax_total, inv.total = totals.subtotal, totals.tax, totals.total
    inv.due_date, inv.notes, inv.terms = body.due_date, body.notes, body.terms
    db.commit()
    return read(db, principal, inv)


def delete_draft(db: Session, principal: Principal, invoice_id: uuid.UUID) -> None:
    inv = load(db, principal, invoice_id, P.INVOICES_MANAGE, lock=True)
    _require_draft(inv)
    db.query(InvoiceItem).filter(InvoiceItem.invoice_id == inv.id).delete()
    audit.record(
        db,
        organisation_id=inv.organisation_id,
        branch_id=inv.branch_id,
        actor=principal,
        action="invoice.draft_deleted",
        entity_type="invoice",
        entity_id=inv.id,
        summary="Draft invoice deleted",
    )
    db.delete(inv)
    db.commit()


def issue(db: Session, principal: Principal, invoice_id: uuid.UUID) -> InvoiceRead:
    inv = load(db, principal, invoice_id, P.INVOICES_MANAGE, lock=True)
    _require_draft(inv)
    if inv.job_card_id:
        job = db.get_one(JobCard, inv.job_card_id)
        if JobStatus(job.status) not in INVOICEABLE:
            raise ConflictError(
                "The job must reach quality inspection before it is invoiced.",
                details={"job_status": job.status},
            )
    lines = db.scalar(
        select(func.count()).select_from(InvoiceItem).where(InvoiceItem.invoice_id == inv.id)
    )
    if not lines:
        raise ConflictError("Add at least one line before issuing.")
    if inv.total <= 0:
        raise ConflictError("The invoice total must be more than zero.")
    on = today(db, inv.organisation_id)
    s = org_settings(db, inv.organisation_id)
    if inv.due_date is None:
        inv.due_date = on + timedelta(days=s.invoice_payment_days)
    elif inv.due_date < on:
        raise ConflictError("The due date is in the past.")
    inv.invoice_number = numbering.allocate(db, inv.organisation_id, numbering.DocumentType.INVOICE)
    inv.status, inv.issue_date = "issued", on
    inv.issued_at, inv.issued_by_user_id = utcnow(), principal.user_id
    audit.record(
        db,
        organisation_id=inv.organisation_id,
        branch_id=inv.branch_id,
        actor=principal,
        action="invoice.issued",
        entity_type="invoice",
        entity_id=inv.id,
        summary=f"Invoice {inv.invoice_number} issued for {inv.currency_code} {inv.total}",
        changes={"total": [None, inv.total], "due_date": [None, inv.due_date]},
    )
    db.commit()
    return read(db, principal, inv)


# --------------------------------------------------------------------------- credit notes


def create_credit_note(
    db: Session, principal: Principal, invoice_id: uuid.UUID, body: CreditNoteCreate
) -> InvoiceRead:
    inv = load(db, principal, invoice_id, P.INVOICES_CREDIT, lock=True)
    if inv.status != "issued":
        raise ConflictError("Only issued invoices can be credited. Edit the draft instead.")
    creditable = inv.total - inv.amount_credited

    if body.full:
        if body.lines:
            raise ConflictError("Give either a full credit or specific lines, not both.")
        if inv.amount_credited > 0:
            raise ConflictError("Part of this invoice is already credited. Credit specific lines.")
        rows = [
            {c: getattr(i, c) for c in ITEM_COLUMNS}
            for i in db.scalars(
                select(InvoiceItem)
                .where(InvoiceItem.invoice_id == inv.id)
                .order_by(InvoiceItem.position)
            )
        ]
        subtotal, tax, total = inv.subtotal, inv.tax_total, inv.total
    else:
        if not body.lines:
            raise ConflictError("Add at least one line to credit.")
        items = [
            SimpleNamespace(kind="fee", part_number=None, **line.model_dump())
            for line in body.lines
        ]
        priced, totals = price_lines(
            db, inv.organisation_id, items, prices_include_tax=inv.prices_include_tax
        )
        rows = [p.fields for p in priced]
        subtotal, tax, total = totals.subtotal, totals.tax, totals.total

    if total <= 0:
        raise ConflictError("The credit total must be more than zero.")
    if total > creditable:
        raise ConflictError(
            "A credit cannot exceed what remains on the invoice.",
            details={"creditable": str(creditable)},
        )
    cn = CreditNote(
        organisation_id=inv.organisation_id,
        invoice_id=inv.id,
        credit_note_number=numbering.allocate(
            db, inv.organisation_id, numbering.DocumentType.CREDIT_NOTE
        ),
        issue_date=today(db, inv.organisation_id),
        reason=body.reason,
        currency_code=inv.currency_code,
        subtotal=subtotal,
        tax_total=tax,
        total=total,
        created_by_user_id=principal.user_id,
    )
    db.add(cn)
    db.flush()
    for pos, r in enumerate(rows):
        # Full credits copy the invoice lines as they are (discount lines stay negative).
        db.add(
            CreditNoteItem(
                credit_note_id=cn.id,
                position=pos,
                **{k: r[k] for k in CREDIT_ITEM_COLUMNS},
            )
        )
    before = inv.amount_credited
    inv.amount_credited = before + total
    audit.record(
        db,
        organisation_id=inv.organisation_id,
        branch_id=inv.branch_id,
        actor=principal,
        action="invoice.credited",
        entity_type="invoice",
        entity_id=inv.id,
        summary=f"Credit note {cn.credit_note_number} for {inv.currency_code} {total} "
        f"on {inv.invoice_number}: {body.reason}",
        changes={"amount_credited": [before, inv.amount_credited]},
    )
    db.commit()
    return read(db, principal, inv)
