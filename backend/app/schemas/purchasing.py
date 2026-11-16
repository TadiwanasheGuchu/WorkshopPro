import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import OptionalEmail, OptionalStr, Schema, UpdateSchema
from app.schemas.inventory import MovementRead, Quantity, Reason, Unit
from app.schemas.job_card import Ref

PoStatus = Literal["draft", "approved", "partially_received", "received", "closed", "cancelled"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Cost = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


# --------------------------------------------------------------------------- suppliers


class SupplierCreate(Schema):
    name: Name
    contact_person: OptionalStr = Field(None, max_length=200)
    phone: OptionalStr = Field(None, max_length=50)
    email: OptionalEmail = None
    address: OptionalStr = Field(None, max_length=1000)
    tax_number: OptionalStr = Field(None, max_length=100)
    account_number: OptionalStr = Field(
        None, max_length=100, description="Your account number with this supplier."
    )
    payment_terms_days: int = Field(30, ge=0, le=365)
    notes: OptionalStr = Field(None, max_length=4000)


class SupplierUpdate(UpdateSchema):
    non_nullable: ClassVar[frozenset[str]] = frozenset({"name", "payment_terms_days"})

    name: Name | None = None
    contact_person: OptionalStr = Field(None, max_length=200)
    phone: OptionalStr = Field(None, max_length=50)
    email: OptionalEmail = None
    address: OptionalStr = Field(None, max_length=1000)
    tax_number: OptionalStr = Field(None, max_length=100)
    account_number: OptionalStr = Field(None, max_length=100)
    payment_terms_days: int | None = Field(None, ge=0, le=365)
    notes: OptionalStr = Field(None, max_length=4000)


class SupplierPartInput(Schema):
    supplier_sku: OptionalStr = Field(None, max_length=100)
    last_cost: Cost | None = None
    lead_time_days: int | None = Field(None, ge=0, le=365)


class SupplierPartRead(BaseModel):
    part: Ref
    sku: str
    unit: Unit
    supplier_sku: str | None
    last_cost: Decimal | None
    lead_time_days: int | None


class SupplierListItem(BaseModel):
    id: uuid.UUID
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    archived_at: datetime | None
    open_orders: int


class SupplierRead(SupplierListItem):
    address: str | None
    tax_number: str | None
    account_number: str | None
    payment_terms_days: int
    notes: str | None
    parts: list[SupplierPartRead]
    received_value_90_days: Decimal
    capabilities: dict[str, bool]


# --------------------------------------------------------------------------- purchase orders


class PoLineInput(Schema):
    part_id: uuid.UUID
    quantity: Quantity
    unit_cost: Cost | None = Field(
        None, description="Defaults to the supplier's last cost, else the part's cost price."
    )


class PoCreate(Schema):
    branch_id: uuid.UUID
    supplier_id: uuid.UUID
    expected_date: date | None = None
    notes: OptionalStr = Field(None, max_length=4000)
    lines: list[PoLineInput] = Field(default_factory=list, max_length=200)


class PoDraftUpdate(Schema):
    version: int
    expected_date: date | None = None
    notes: OptionalStr = Field(None, max_length=4000)
    lines: list[PoLineInput] = Field(max_length=200)


class VersionBody(Schema):
    version: int


class CloseRequest(Schema):
    version: int
    reason: Reason


class ReceiveLine(Schema):
    po_line_id: uuid.UUID
    quantity: Quantity
    discrepancy: OptionalStr = Field(
        None, max_length=500, description="e.g. 'Box damaged', 'Short by 2, back-ordered'."
    )


class ReceiveRequest(Schema):
    location_id: uuid.UUID
    delivery_reference: OptionalStr = Field(None, max_length=100)
    supplier_invoice_reference: OptionalStr = Field(None, max_length=100)
    notes: OptionalStr = Field(None, max_length=2000)
    lines: list[ReceiveLine] = Field(min_length=1, max_length=200)


class ReturnLine(Schema):
    po_line_id: uuid.UUID
    quantity: Quantity


class SupplierReturnCreate(Schema):
    location_id: uuid.UUID
    reason: Reason
    reference: OptionalStr = Field(None, max_length=100)
    lines: list[ReturnLine] = Field(min_length=1, max_length=200)


class PoLineRead(BaseModel):
    id: uuid.UUID
    part: Ref
    sku: str
    unit: Unit
    supplier_sku: str | None
    quantity_ordered: Decimal
    quantity_received: Decimal
    quantity_returned: Decimal
    outstanding: Decimal
    unit_cost: Decimal
    line_total: Decimal


class GrnLineRead(BaseModel):
    part: Ref
    sku: str
    quantity: Decimal
    unit_cost: Decimal
    discrepancy: str | None


class GrnRead(BaseModel):
    id: uuid.UUID
    grn_number: str
    location: Ref
    received_at: datetime
    received_by: str
    delivery_reference: str | None
    supplier_invoice_reference: str | None
    notes: str | None
    total: Decimal
    lines: list[GrnLineRead]


class SupplierReturnRead(BaseModel):
    id: uuid.UUID
    location: Ref
    reason: str
    reference: str | None
    total: Decimal
    created_by: str
    created_at: datetime
    lines: list[GrnLineRead]


class PoCapabilities(BaseModel):
    edit: bool
    approve: bool
    receive: bool
    return_goods: bool
    cancel: bool
    close: bool


class PoListItem(BaseModel):
    id: uuid.UUID
    po_number: str
    status: PoStatus
    supplier: Ref
    branch: Ref
    expected_date: date | None
    is_overdue: bool
    total: Decimal
    currency_code: str
    created_at: datetime


class PoRead(PoListItem):
    notes: str | None
    received_value: Decimal
    returned_value: Decimal
    lines: list[PoLineRead]
    receipts: list[GrnRead]
    returns: list[SupplierReturnRead]
    created_by: str
    approved_by: str | None
    approved_at: datetime | None
    closed_reason: str | None
    version: int
    locations: list[Ref]
    capabilities: PoCapabilities


class ReceiveResult(BaseModel):
    order: PoRead
    movements: list[MovementRead]
