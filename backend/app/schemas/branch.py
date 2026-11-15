import uuid
from datetime import datetime, time
from typing import Annotated, Self

from pydantic import BeforeValidator, Field, StringConstraints, model_validator

from app.schemas.common import Name, OptionalEmail, OptionalStr, ReadSchema, Schema, UpdateSchema


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


BranchCode = Annotated[
    str,
    BeforeValidator(_upper),
    StringConstraints(pattern=r"^[A-Z0-9-]{1,12}$"),
]


class BranchFields(Schema):
    email: OptionalEmail = None
    phone: OptionalStr = Field(None, max_length=50)
    address_line1: OptionalStr = Field(None, max_length=200)
    address_line2: OptionalStr = Field(None, max_length=200)
    city: OptionalStr = Field(None, max_length=100)
    postal_code: OptionalStr = Field(None, max_length=20)


class BranchCreate(BranchFields):
    name: Name
    code: BranchCode = Field(
        description="Short code, e.g. WHK or SWK-01. Letters, digits, hyphens."
    )


class BranchUpdate(BranchFields, UpdateSchema):
    non_nullable = frozenset({"name", "code"})

    name: Name | None = None
    code: BranchCode | None = None


class BranchRead(ReadSchema):
    id: uuid.UUID
    name: str
    code: str
    email: str | None
    phone: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    postal_code: str | None
    archived_at: datetime | None
    created_at: datetime


class OperatingHoursDay(Schema):
    weekday: int = Field(ge=0, le=6, description="0 = Monday … 6 = Sunday")
    is_closed: bool
    opens_at: time | None = None
    closes_at: time | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.is_closed:
            self.opens_at = self.closes_at = None
        elif self.opens_at is None or self.closes_at is None:
            raise ValueError("Opening and closing times are required on open days.")
        elif self.opens_at >= self.closes_at:
            raise ValueError("Closing time must be after opening time.")
        return self


class OperatingHoursRead(ReadSchema):
    weekday: int
    is_closed: bool
    opens_at: time | None
    closes_at: time | None


class OperatingHoursUpdate(Schema):
    days: list[OperatingHoursDay] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def _all_weekdays(self) -> Self:
        if sorted(d.weekday for d in self.days) != list(range(7)):
            raise ValueError("Provide each weekday (0-6) exactly once.")
        return self


class BranchDetail(BranchRead):
    operating_hours: list[OperatingHoursRead]


class ServiceBayRead(ReadSchema):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool


class ServiceBayCreate(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: OptionalStr = Field(None, max_length=300)


class ServiceBayUpdate(UpdateSchema):
    non_nullable = frozenset({"name", "is_active"})

    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    description: OptionalStr = Field(None, max_length=300)
    is_active: bool | None = None
