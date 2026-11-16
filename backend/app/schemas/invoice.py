import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.schemas.common import OptionalStr, Schema
from app.schemas.job_card import Ref
from app.schemas.quotation import ItemInput, ItemRead, Text500

Method = Literal["cash", "eft", "card", "mobile", "cheque", "other"]
PaymentStatus = Literal["draft", "unpaid", "partially_paid", "paid", "credited", "overpaid"]
Money = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class InvoiceDraftUpdate(Schema):
    due_date: date | None = None
    notes: OptionalStr = Field(None, max_length=4000)
    terms: OptionalStr = Field(None, max_length=4000)
    items: list[ItemInput] = Field(max_length=300)


class CreditLine(Schema):
    description: Text500
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit_price: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    tax_rate_id: uuid.UUID | None = None


class CreditNoteCreate(Schema):
    reason: Reason
    # Either credit the whole invoice (copies its lines) or give specific lines.
    full: bool = False
    lines: list[CreditLine] = Field(default_factory=list, max_length=100)


class AllocationInput(Schema):
    invoice_id: uuid.UUID
    amount: Money


class PaymentCreate(Schema):
    branch_id: uuid.UUID
    customer_id: uuid.UUID
    method: Method
    amount: Money
    received_at: AwareDatetime | None = None
    reference: OptionalStr = Field(None, max_length=100)
    notes: OptionalStr = Field(None, max_length=1000)
    allocations: list[AllocationInput] = Field(default_factory=list, max_length=50)


class AllocateRequest(Schema):
    allocations: list[AllocationInput] = Field(min_length=1, max_length=50)


class ReverseRequest(Schema):
    reason: Reason


class RefundCreate(Schema):
    invoice_id: uuid.UUID
    method: Method
    amount: Money
    reference: OptionalStr = Field(None, max_length=100)
    reason: Reason


# --------------------------------------------------------------------------- reads


class CreditNoteRead(BaseModel):
    id: uuid.UUID
    credit_note_number: str
    issue_date: date
    reason: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    created_by: str


class InvoicePaymentLine(BaseModel):
    payment_id: uuid.UUID
    receipt_number: str
    kind: Literal["payment", "refund", "reversal"]
    method: Method
    received_at: datetime
    amount: Decimal  # allocated to this invoice; negative for refunds/reversals


class InvoiceCapabilities(BaseModel):
    edit: bool
    issue: bool
    delete: bool
    credit: bool
    record_payment: bool
    refund: bool


class InvoiceListItem(BaseModel):
    id: uuid.UUID
    invoice_number: str | None
    status: Literal["draft", "issued"]
    payment_status: PaymentStatus
    customer: Ref
    job_card: Ref | None
    issue_date: date | None
    due_date: date | None
    is_overdue: bool
    currency_code: str
    total: Decimal
    balance_due: Decimal


class InvoiceRead(InvoiceListItem):
    branch: Ref
    prices_include_tax: bool
    items: list[ItemRead]
    subtotal: Decimal
    tax_total: Decimal
    amount_paid: Decimal
    amount_credited: Decimal
    notes: str | None
    terms: str | None
    issued_at: datetime | None
    issued_by: str | None
    quotation_version_id: uuid.UUID | None
    credit_notes: list[CreditNoteRead]
    payments: list[InvoicePaymentLine]
    capabilities: InvoiceCapabilities


class AllocationRead(BaseModel):
    invoice_id: uuid.UUID
    invoice_number: str | None
    amount: Decimal


class PaymentRead(BaseModel):
    id: uuid.UUID
    receipt_number: str
    kind: Literal["payment", "refund", "reversal"]
    method: Method
    amount: Decimal
    currency_code: str
    received_at: datetime
    reference: str | None
    notes: str | None
    branch: Ref
    customer: Ref
    recorded_by: str
    allocations: list[AllocationRead]
    unallocated: Decimal
    reversed_by_receipt: str | None
    reverses_receipt: str | None


class CustomerBalance(BaseModel):
    """Amounts owed per issued invoices and payments not yet allocated, in the
    organisation's currency."""

    customer_id: uuid.UUID
    currency_code: str
    outstanding: Decimal
    unallocated_credit: Decimal
    open_invoices: list[InvoiceListItem]
