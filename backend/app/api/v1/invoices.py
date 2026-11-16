import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, Paging
from app.schemas.common import Page
from app.schemas.invoice import (
    AllocateRequest,
    CreditNoteCreate,
    CustomerBalance,
    InvoiceDraftUpdate,
    InvoiceListItem,
    InvoiceRead,
    PaymentCreate,
    PaymentRead,
    RefundCreate,
    ReverseRequest,
)
from app.services import invoices, payments

router = APIRouter(tags=["invoices and payments"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9_\-:.]+$",
        description=(
            "Unique per intended operation (e.g. a UUID generated when the form opens). "
            "Retrying with the same key and body returns the original record."
        ),
    ),
]


def _replayed(response: Response, created: bool) -> None:
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"


# --------------------------------------------------------------------------- invoices


@router.get("/invoices", response_model=Page[InvoiceListItem], summary="List invoices")
def list_invoices(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    status: Literal["draft", "issued", "outstanding", "overdue", "paid"] | None = None,
    customer_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[InvoiceListItem]:
    items, total = invoices.list_invoices(
        db, principal, paging, status=status, customer_id=customer_id, search=search
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/job-cards/{job_id}/invoices",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a draft invoice for the job",
    description=(
        "The first invoice for a job is prefilled from its approved quotation, if any. "
        "Only one draft per job at a time."
    ),
)
def create(job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> InvoiceRead:
    return invoices.create_for_job(db, principal, job_id)


@router.get(
    "/job-cards/{job_id}/invoices",
    response_model=list[InvoiceListItem],
    summary="The job's invoices",
)
def for_job(job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[InvoiceListItem]:
    return invoices.for_job(db, principal, job_id)


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead, summary="Invoice")
def get(invoice_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> InvoiceRead:
    return invoices.get_invoice(db, principal, invoice_id)


@router.put(
    "/invoices/{invoice_id}/draft",
    response_model=InvoiceRead,
    summary="Replace the draft's lines and details",
    description="Totals and tax are calculated by the server. Issued invoices cannot change.",
)
def save_draft(
    invoice_id: uuid.UUID, body: InvoiceDraftUpdate, principal: CurrentPrincipal, db: DbSession
) -> InvoiceRead:
    return invoices.save_draft(db, principal, invoice_id, body)


@router.delete(
    "/invoices/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft invoice",
    description="Only drafts (which have no number) can be deleted.",
)
def delete_draft(invoice_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> None:
    invoices.delete_draft(db, principal, invoice_id)


@router.post(
    "/invoices/{invoice_id}/issue",
    response_model=InvoiceRead,
    summary="Issue the invoice",
    description=(
        "Allocates the invoice number and fixes the issue and due dates. The job must have "
        "reached quality inspection. After this the invoice is immutable."
    ),
)
def issue(invoice_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> InvoiceRead:
    return invoices.issue(db, principal, invoice_id)


@router.post(
    "/invoices/{invoice_id}/credit-notes",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a credit note",
    description="Credits the whole invoice or specific amounts; never more than remains.",
)
def credit(
    invoice_id: uuid.UUID, body: CreditNoteCreate, principal: CurrentPrincipal, db: DbSession
) -> InvoiceRead:
    return invoices.create_credit_note(db, principal, invoice_id, body)


@router.get(
    "/customers/{customer_id}/balance",
    response_model=CustomerBalance,
    summary="Customer's outstanding balance",
    description=(
        "outstanding: unpaid balances of issued invoices. unallocated_credit: money received "
        "but not yet allocated, plus overpayments."
    ),
)
def customer_balance(
    customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> CustomerBalance:
    return payments.customer_balance(db, principal, customer_id)


# --------------------------------------------------------------------------- payments


@router.get("/payments", response_model=Page[PaymentRead], summary="List payments and refunds")
def list_payments(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    customer_id: uuid.UUID | None = None,
    kind: Literal["payment", "refund", "reversal"] | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[PaymentRead]:
    items, total = payments.list_payments(
        db, principal, paging, customer_id=customer_id, kind=kind, search=search
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/payments",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a payment received",
    description=(
        "Records money received; no card processing. Requires an Idempotency-Key. "
        "Any amount not allocated to invoices stays as customer credit."
    ),
)
def record_payment(
    body: PaymentCreate,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> PaymentRead:
    payment, created = payments.record_payment(db, principal, body, idempotency_key)
    _replayed(response, created)
    return payment


@router.get("/payments/{payment_id}", response_model=PaymentRead, summary="Payment")
def get_payment(payment_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> PaymentRead:
    return payments.get_payment(db, principal, payment_id)


@router.post(
    "/payments/{payment_id}/allocations",
    response_model=PaymentRead,
    summary="Allocate unallocated credit to invoices",
)
def allocate(
    payment_id: uuid.UUID, body: AllocateRequest, principal: CurrentPrincipal, db: DbSession
) -> PaymentRead:
    return payments.allocate_credit(db, principal, payment_id, body)


@router.post(
    "/payments/{payment_id}/reverse",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Reverse a payment recorded in error",
    description="Creates a linked reversal and undoes every allocation. Requires a reason.",
)
def reverse(
    payment_id: uuid.UUID,
    body: ReverseRequest,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> PaymentRead:
    payment, created = payments.reverse(db, principal, payment_id, body, idempotency_key)
    _replayed(response, created)
    return payment


@router.post(
    "/refunds",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Refund an overpayment",
    description="Only what was overpaid on the invoice (for example after a credit note).",
)
def refund(
    body: RefundCreate,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> PaymentRead:
    payment, created = payments.refund(db, principal, body, idempotency_key)
    _replayed(response, created)
    return payment
