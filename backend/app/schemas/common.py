from typing import Annotated, Any, ClassVar, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _lower_email(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def _check_password(value: str) -> str:
    if not value.strip():
        raise ValueError("Password cannot be only spaces.")
    return value


RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OptionalStr = Annotated[str | None, BeforeValidator(_blank_to_none)]
# Emails are stored lowercased; lookups are case-insensitive (CITEXT) regardless.
OptionalEmail = Annotated[
    EmailStr | None, BeforeValidator(_lower_email), BeforeValidator(_blank_to_none)
]
Email = Annotated[EmailStr, BeforeValidator(_lower_email), StringConstraints(max_length=254)]
Password = Annotated[
    str,
    StringConstraints(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
    AfterValidator(_check_password),
]


class Schema(BaseModel):
    """Base for request bodies: reject unknown fields so typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


class UpdateSchema(Schema):
    """Partial update body. Fields left out are unchanged; fields listed in
    `non_nullable` may be omitted but not explicitly set to null."""

    non_nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_nulls(self) -> Self:
        for name in self.non_nullable & self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be empty.")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
