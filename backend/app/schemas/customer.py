import datetime as dt
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, model_validator

from app.schemas.common import OptionalStr, ReadSchema, Schema, UpdateSchema

CustomerType = Literal["individual", "company"]
ContactMethod = Literal["phone", "whatsapp", "email", "sms"]
ConsentChannel = Literal["whatsapp", "sms", "email", "marketing"]
ConsentStatus = Literal["granted", "withdrawn"]
ConsentMethod = Literal["verbal", "written", "signed_form", "customer_portal", "other"]
FuelType = Literal["petrol", "diesel", "hybrid", "electric", "lpg", "other"]
Transmission = Literal["manual", "automatic", "other"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_phone(value: str) -> str:
    """Keep digits and a leading +. '081 234 5678' -> '0812345678'."""
    cleaned = value.strip()
    plus = cleaned.startswith("+")
    digits = re.sub(r"\D", "", cleaned)
    if not 6 <= len(digits) <= 15:
        raise ValueError("Enter a phone number with 6 to 15 digits.")
    return f"+{digits}" if plus else digits


def normalise_registration(value: str) -> str:
    """Uppercase, single spaces. Namibian plates look like 'N 12345 W'; foreign and
    older formats vary, so only the character set and length are checked."""
    cleaned = re.sub(r"\s+", " ", value.strip().upper())
    if not re.fullmatch(r"[A-Z0-9 -]{2,15}", cleaned) or not re.search(r"[A-Z0-9]", cleaned):
        raise ValueError("Use 2-15 letters, digits, spaces or hyphens.")
    return cleaned


def registration_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def normalise_vin(value: str) -> str:
    """Modern VINs have 17 characters without I, O or Q; older chassis numbers are
    shorter, so 5-17 letters/digits are accepted."""
    cleaned = re.sub(r"[\s-]", "", value.strip().upper())
    if not re.fullmatch(r"[A-Z0-9]{5,17}", cleaned):
        raise ValueError("Use 5-17 letters and digits.")
    if len(cleaned) == 17 and re.search(r"[IOQ]", cleaned):
        raise ValueError("A 17-character VIN cannot contain the letters I, O or Q.")
    return cleaned


def _check_year(value: int | None) -> int | None:
    if value is not None and not 1900 <= value <= datetime.now(UTC).year + 1:
        raise ValueError("Enter a year between 1900 and next year.")
    return value


Registration = Annotated[str, AfterValidator(normalise_registration)]
Vin = Annotated[str, AfterValidator(normalise_vin)]
Year = Annotated[int | None, AfterValidator(_check_year)]


def _blank(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


# --------------------------------------------------------------------------- contacts


class ContactInput(Schema):
    kind: Literal["phone", "email"]
    value: str = Field(min_length=3, max_length=254)
    label: OptionalStr = Field(None, max_length=50)
    is_primary: bool = False

    @model_validator(mode="after")
    def _normalise(self) -> Self:
        if self.kind == "phone":
            self.value = normalise_phone(self.value)
        else:
            email = self.value.strip().lower()
            if not _EMAIL_RE.match(email):
                raise ValueError("Enter a valid email address.")
            self.value = email
        return self


class AddressInput(Schema):
    kind: Literal["physical", "postal"]
    line1: str = Field(min_length=1, max_length=200)
    line2: OptionalStr = Field(None, max_length=200)
    city: OptionalStr = Field(None, max_length=100)
    region: OptionalStr = Field(None, max_length=100)
    postal_code: OptionalStr = Field(None, max_length=20)


class ContactRead(ReadSchema):
    id: uuid.UUID
    kind: str
    label: str | None
    value: str
    is_primary: bool


class AddressRead(ReadSchema):
    id: uuid.UUID
    kind: str
    line1: str
    line2: str | None
    city: str | None
    region: str | None
    postal_code: str | None


def _check_contacts(contacts: list[ContactInput] | None) -> None:
    if not contacts:
        return
    for kind in ("phone", "email"):
        if sum(1 for c in contacts if c.kind == kind and c.is_primary) > 1:
            raise ValueError(f"Only one {kind} can be primary.")
    values = [(c.kind, c.value) for c in contacts]
    if len(values) != len(set(values)):
        raise ValueError("The same phone number or email is listed twice.")


# --------------------------------------------------------------------------- customers


class CustomerFields(Schema):
    first_name: OptionalStr = Field(None, max_length=200)
    last_name: OptionalStr = Field(None, max_length=200)
    company_name: OptionalStr = Field(None, max_length=200)
    contact_person: OptionalStr = Field(None, max_length=200)
    registration_number: OptionalStr = Field(None, max_length=100)
    tax_number: OptionalStr = Field(None, max_length=100)
    notes: OptionalStr = Field(None, max_length=4000)


class CustomerCreate(CustomerFields):
    customer_type: CustomerType
    preferred_contact_method: ContactMethod = "phone"
    contacts: list[ContactInput] = Field(default_factory=list, max_length=10)
    addresses: list[AddressInput] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.customer_type == "individual" and not self.last_name:
            raise ValueError("Enter the customer's surname.")
        if self.customer_type == "company" and not self.company_name:
            raise ValueError("Enter the company name.")
        _check_contacts(self.contacts)
        return self


class CustomerUpdate(CustomerFields, UpdateSchema):
    non_nullable = frozenset({"customer_type", "preferred_contact_method"})

    customer_type: CustomerType | None = None
    preferred_contact_method: ContactMethod | None = None
    # When provided, these replace the existing lists.
    contacts: list[ContactInput] | None = Field(None, max_length=10)
    addresses: list[AddressInput] | None = Field(None, max_length=4)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _check_contacts(self.contacts)
        return self


class CustomerSummary(BaseModel):
    id: uuid.UUID
    customer_type: CustomerType
    display_name: str
    primary_phone: str | None
    primary_email: str | None
    vehicle_count: int
    archived_at: datetime | None
    created_at: datetime


class ConsentInput(Schema):
    channel: ConsentChannel
    status: ConsentStatus
    method: ConsentMethod
    evidence: Annotated[str | None, BeforeValidator(_blank)] = Field(
        None,
        max_length=500,
        description="Where the consent is recorded, e.g. 'Signed intake form #231'.",
    )


class ConsentRead(BaseModel):
    id: uuid.UUID
    channel: ConsentChannel
    status: ConsentStatus
    method: ConsentMethod
    evidence: str | None
    recorded_at: datetime
    recorded_by: str | None


class VehicleBrief(BaseModel):
    id: uuid.UUID
    registration_number: str | None
    vin: str | None
    make: str
    model: str
    year: int | None
    archived_at: datetime | None


class CustomerDetail(BaseModel):
    id: uuid.UUID
    customer_type: CustomerType
    display_name: str
    first_name: str | None
    last_name: str | None
    company_name: str | None
    contact_person: str | None
    registration_number: str | None
    tax_number: str | None
    preferred_contact_method: ContactMethod
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    contacts: list[ContactRead]
    addresses: list[AddressRead]
    # Current consent per channel (latest record). Full history: GET .../consents.
    consents: list[ConsentRead]
    vehicles: list[VehicleBrief]


# --------------------------------------------------------------------------- vehicles


class VehicleFields(Schema):
    engine_number: OptionalStr = Field(None, max_length=50)
    variant: OptionalStr = Field(None, max_length=100)
    year: Year = None
    fuel_type: FuelType | None = None
    transmission: Transmission | None = None
    colour: OptionalStr = Field(None, max_length=40)
    existing_damage: OptionalStr = Field(None, max_length=4000)
    notes: OptionalStr = Field(None, max_length=4000)
    next_service_due_date: dt.date | None = Field(
        None, description="When the next service is due; the customer is reminded beforehand."
    )
    next_service_due_km: int | None = Field(None, ge=0, le=5_000_000)


class VehicleCreate(VehicleFields):
    customer_id: uuid.UUID
    registration_number: Annotated[Registration | None, BeforeValidator(_blank)] = None
    vin: Annotated[Vin | None, BeforeValidator(_blank)] = None
    make: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    odometer_km: int | None = Field(None, ge=0, le=5_000_000)

    @model_validator(mode="after")
    def _identifier(self) -> Self:
        if not self.registration_number and not self.vin:
            raise ValueError("Enter a registration number or a VIN / chassis number.")
        self.make = self.make.strip()
        self.model = self.model.strip()
        return self


class VehicleUpdate(VehicleFields, UpdateSchema):
    non_nullable = frozenset({"make", "model"})

    registration_number: Annotated[Registration | None, BeforeValidator(_blank)] = None
    vin: Annotated[Vin | None, BeforeValidator(_blank)] = None
    make: str | None = Field(None, min_length=1, max_length=60)
    model: str | None = Field(None, min_length=1, max_length=60)
    odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    odometer_correction_reason: OptionalStr = Field(
        None,
        max_length=300,
        description="Required when lowering the odometer reading (e.g. a typing error).",
    )


class VehicleTransfer(Schema):
    customer_id: uuid.UUID
    note: OptionalStr = Field(None, max_length=300)


class CustomerBrief(BaseModel):
    id: uuid.UUID
    display_name: str


class VehicleRead(BaseModel):
    id: uuid.UUID
    customer: CustomerBrief
    registration_number: str | None
    vin: str | None
    engine_number: str | None
    make: str
    model: str
    variant: str | None
    year: int | None
    fuel_type: FuelType | None
    transmission: Transmission | None
    colour: str | None
    odometer_km: int | None
    next_service_due_date: dt.date | None
    next_service_due_km: int | None
    odometer_recorded_at: datetime | None
    existing_damage: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime


class OwnershipRead(BaseModel):
    customer: CustomerBrief
    started_at: datetime
    ended_at: datetime | None
    note: str | None
