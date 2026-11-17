import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Email, OptionalStr, Schema
from app.schemas.customer import ContactMethod
from app.schemas.quotation import ItemRead

# --------------------------------------------------------------------------- auth (customer)


class LinkRequest(Schema):
    email: Email


class ConsumeRequest(Schema):
    token: str = Field(min_length=20, max_length=100)


# --------------------------------------------------------------------------- staff side


class PortalInvite(Schema):
    email: Email = Field(description="One of the customer's email addresses.")


class PortalAccess(BaseModel):
    enabled: bool
    email: str | None
    invited_at: datetime | None
    last_sign_in_at: datetime | None


# --------------------------------------------------------------------------- customer reads


class PortalMe(BaseModel):
    customer_name: str
    email: str
    organisation_name: str
    organisation_phone: str | None
    organisation_email: str | None
    phone: str | None
    preferred_contact_method: ContactMethod
    whatsapp_consent: bool
    email_consent: bool
    timezone: str
    date_format: str


class PortalMeUpdate(Schema):
    phone: OptionalStr = Field(None, max_length=30)
    preferred_contact_method: ContactMethod | None = None
    whatsapp_consent: bool | None = None
    email_consent: bool | None = None


class PortalVehicle(BaseModel):
    id: uuid.UUID
    label: str
    registration_number: str | None
    vin: str | None
    make: str
    model: str
    year: int | None
    odometer_km: int | None


class PortalJob(BaseModel):
    id: uuid.UUID
    job_number: str
    vehicle: str
    status: str
    status_label: str
    received_at: datetime
    promised_at: datetime | None
    collected_at: datetime | None
    complaint: str


class PortalStatusStep(BaseModel):
    label: str
    at: datetime


class PortalDocumentRef(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    total: Decimal | None = None
    balance_due: Decimal | None = None
    date: date | datetime | None = None


class PortalJobDetail(PortalJob):
    work_performed: str | None
    history: list[PortalStatusStep]
    quotation: PortalDocumentRef | None
    invoices: list[PortalDocumentRef]
    inspections: list[PortalDocumentRef]


class PortalQuotation(BaseModel):
    id: uuid.UUID
    quote_number: str
    version_number: int
    status: Literal["sent", "approved", "rejected", "expired"]
    job_number: str
    vehicle: str
    currency_code: str
    prices_include_tax: bool
    valid_until: date | None
    items: list[ItemRead]
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    notes: str | None
    terms: str | None
    decision: Literal["approved", "rejected"] | None
    decided_at: datetime | None
    can_decide: bool


class PortalDecision(Schema):
    decision: Literal["approved", "rejected"]
    accept_terms: bool = False
    comments: OptionalStr = Field(None, max_length=2000)


class PortalInvoice(BaseModel):
    id: uuid.UUID
    invoice_number: str
    job_number: str | None
    issue_date: date
    due_date: date | None
    currency_code: str
    total: Decimal
    balance_due: Decimal
    payment_status: str
    is_overdue: bool
    receipts: list[PortalDocumentRef]


class PortalHome(BaseModel):
    me: PortalMe
    vehicles: list[PortalVehicle]
    open_jobs: list[PortalJob]
    quotations_to_review: list[PortalDocumentRef]
    outstanding: Decimal
    currency_code: str
