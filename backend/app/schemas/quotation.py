import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.common import OptionalStr, Schema
from app.schemas.job_card import Ref, VehicleRef

Kind = Literal["labour", "part", "fee", "discount"]
VersionStatus = Literal[
    "draft", "sent", "approved", "rejected", "superseded", "withdrawn", "expired"
]
StaffMethod = Literal["in_person", "phone", "email", "whatsapp", "other"]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class ItemInput(Schema):
    kind: Kind
    description: Text500
    part_number: OptionalStr = Field(None, max_length=100)
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    tax_rate_id: uuid.UUID | None = None


class DraftUpdate(Schema):
    """Replace the content of a draft version."""

    valid_until: date | None = None
    terms: OptionalStr = Field(None, max_length=4000)
    notes: OptionalStr = Field(None, max_length=4000)
    items: list[ItemInput] = Field(max_length=200)


class SendRequest(Schema):
    email_customer: bool = Field(
        True,
        description="Send the approval link to the customer by WhatsApp or email, following "
        "their consent and preference.",
    )


class ReviseRequest(Schema):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class StaffDecision(Schema):
    decision: Literal["approved", "rejected"]
    method: StaffMethod
    customer_name: Name
    evidence: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)
    ] = Field(description="e.g. 'Signed printed quotation', 'Phoned 081 234 5678 at 10:42'.")
    comments: OptionalStr = Field(None, max_length=2000)


class PublicDecision(Schema):
    decision: Literal["approved", "rejected"]
    customer_name: Name
    comments: OptionalStr = Field(None, max_length=2000)
    accept_terms: bool = False

    @model_validator(mode="after")
    def _terms(self) -> Self:
        if self.decision == "approved" and not self.accept_terms:
            raise ValueError("Confirm that you accept the quotation and its terms.")
        return self


# --------------------------------------------------------------------------- reads


class ItemRead(BaseModel):
    id: uuid.UUID
    kind: Kind
    description: str
    part_number: str | None
    quantity: Decimal
    unit_price: Decimal
    tax_rate_id: uuid.UUID | None
    tax_rate_name: str | None
    tax_rate_percent: Decimal
    line_subtotal: Decimal
    line_tax: Decimal
    line_total: Decimal


class DecisionRead(BaseModel):
    decision: Literal["approved", "rejected"]
    method: str
    total: Decimal
    currency_code: str
    customer_name: str
    evidence: str | None
    comments: str | None
    recorded_by: str | None
    decided_at: datetime


class LinkRead(BaseModel):
    expires_at: datetime
    first_viewed_at: datetime | None
    last_viewed_at: datetime | None
    view_count: int
    used_at: datetime | None
    revoked_at: datetime | None


class VersionRead(BaseModel):
    id: uuid.UUID
    version_number: int
    status: VersionStatus
    currency_code: str
    prices_include_tax: bool
    valid_until: date | None
    terms: str | None
    notes: str | None
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    sent_at: datetime | None
    sent_by: str | None
    created_at: datetime
    revision_reason: str | None
    items: list[ItemRead]
    decision: DecisionRead | None
    link: LinkRead | None


class VersionSummary(BaseModel):
    id: uuid.UUID
    version_number: int
    status: VersionStatus
    total: Decimal
    sent_at: datetime | None


class QuotationCapabilities(BaseModel):
    edit: bool
    send: bool
    revise: bool
    record_decision: bool


class QuotationRead(BaseModel):
    id: uuid.UUID
    quote_number: str
    branch: Ref
    job_card: Ref
    customer: Ref
    customer_email: str | None
    vehicle: VehicleRef
    current: VersionRead
    versions: list[VersionSummary]
    capabilities: QuotationCapabilities


class SendResult(BaseModel):
    quotation: QuotationRead
    approval_url: str = Field(description="Shown once. Share it with the customer.")
    emailed_to: str | None = Field(
        description="Where the link is being sent (email address or WhatsApp number), if any."
    )
    notification_channel: Literal["email", "whatsapp", "none"] | None
    notification_skipped: str | None = Field(description="Why the customer was not notified.")


class QuotationListItem(BaseModel):
    id: uuid.UUID
    quote_number: str
    version_number: int
    status: VersionStatus
    total: Decimal
    currency_code: str
    customer: Ref
    vehicle: VehicleRef
    job_card: Ref
    updated_at: datetime


class PublicItem(BaseModel):
    kind: Kind
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate_percent: Decimal
    line_total: Decimal


class PublicQuotation(BaseModel):
    """What the customer sees on the approval page. Contains no internal IDs."""

    organisation_name: str
    organisation_phone: str | None
    organisation_email: str | None
    branch_name: str
    quote_number: str
    version_number: int
    status: VersionStatus
    customer_name: str
    vehicle: str
    currency_code: str
    prices_include_tax: bool
    items: list[PublicItem]
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    valid_until: date | None
    terms: str | None
    notes: str | None
    can_decide: bool
    decision: Literal["approved", "rejected"] | None
    decided_at: datetime | None
