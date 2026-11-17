import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, Field, StringConstraints

from app.schemas.common import (
    Name,
    OptionalEmail,
    OptionalStr,
    ReadSchema,
    Schema,
    UpdateSchema,
)
from app.services.numbering import DocumentType

DateFormat = Literal["DD/MM/YYYY", "YYYY-MM-DD", "MM/DD/YYYY"]


def _valid_timezone(value: str) -> str:
    if value not in available_timezones():
        raise ValueError("Unknown time zone.")
    return value


Timezone = Annotated[str, AfterValidator(_valid_timezone)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class OrganisationRead(ReadSchema):
    id: uuid.UUID
    name: str
    legal_name: str | None
    registration_number: str | None
    tax_number: str | None
    email: str | None
    phone: str | None
    website: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    postal_code: str | None
    country_code: str


class OrganisationUpdate(UpdateSchema):
    non_nullable = frozenset({"name", "country_code"})

    name: Name | None = None
    legal_name: OptionalStr = Field(None, max_length=200)
    registration_number: OptionalStr = Field(None, max_length=100)
    tax_number: OptionalStr = Field(None, max_length=100)
    email: OptionalEmail = None
    phone: OptionalStr = Field(None, max_length=50)
    website: OptionalStr = Field(None, max_length=200)
    address_line1: OptionalStr = Field(None, max_length=200)
    address_line2: OptionalStr = Field(None, max_length=200)
    city: OptionalStr = Field(None, max_length=100)
    postal_code: OptionalStr = Field(None, max_length=20)
    country_code: CountryCode | None = None


class SettingsRead(ReadSchema):
    currency_code: str
    timezone: str
    date_format: str
    prices_include_tax: bool
    document_footer: str | None
    quotation_validity_days: int
    quotation_terms: str | None
    invoice_payment_days: int
    service_reminder_days: int
    invoice_terms: str | None


class SettingsUpdate(UpdateSchema):
    non_nullable = frozenset(
        {
            "currency_code",
            "timezone",
            "date_format",
            "prices_include_tax",
            "quotation_validity_days",
            "invoice_payment_days",
            "service_reminder_days",
        }
    )

    currency_code: CurrencyCode | None = None
    timezone: Timezone | None = None
    date_format: DateFormat | None = None
    prices_include_tax: bool | None = None
    document_footer: OptionalStr = Field(None, max_length=1000)
    quotation_validity_days: int | None = Field(None, ge=1, le=365)
    quotation_terms: OptionalStr = Field(None, max_length=4000)
    invoice_payment_days: int | None = Field(
        None, ge=0, le=365, description="Days after issue that an invoice falls due (0 = on issue)."
    )
    invoice_terms: OptionalStr = Field(None, max_length=4000)
    service_reminder_days: int | None = Field(
        None, ge=1, le=90, description="Days before a vehicle's service due date to remind."
    )


class TaxRateRead(ReadSchema):
    id: uuid.UUID
    name: str
    rate_percent: Decimal
    description: str | None
    is_default: bool
    is_active: bool
    created_at: datetime


RatePercent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class TaxRateCreate(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    rate_percent: RatePercent
    description: OptionalStr = Field(None, max_length=300)
    is_default: bool = False


class TaxRateUpdate(UpdateSchema):
    non_nullable = frozenset({"name", "rate_percent", "is_default", "is_active"})

    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    rate_percent: RatePercent | None = None
    description: OptionalStr = Field(None, max_length=300)
    is_default: bool | None = None
    is_active: bool | None = None


class DocumentSequenceRead(ReadSchema):
    document_type: DocumentType
    label: str
    prefix: str
    next_number: int
    padding: int
    example: str
    last_allocated_at: datetime | None


class DocumentSequenceUpdate(UpdateSchema):
    non_nullable = frozenset({"prefix", "padding", "next_number"})

    prefix: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]{0,10}$")] | None = None
    padding: int | None = Field(None, ge=1, le=10)
    next_number: int | None = Field(None, ge=1, le=999_999_999)
