import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import OptionalStr, Schema

Result = Literal["pass", "attention", "fail", "not_inspected"]
Kind = Literal["intake", "quality", "other"]


Section = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class TemplateItemInput(Schema):
    section: Section
    label: Label
    guidance: OptionalStr = Field(None, max_length=500)


class TemplateInput(Schema):
    name: Name
    description: OptionalStr = Field(None, max_length=500)
    is_default: bool = False
    items: list[TemplateItemInput] = Field(min_length=1, max_length=300)


class TemplateItemRead(BaseModel):
    id: uuid.UUID
    section: str
    label: str
    guidance: str | None


class TemplateRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_default: bool
    archived_at: datetime | None
    item_count: int
    items: list[TemplateItemRead] | None = None


class InspectionCreate(Schema):
    template_id: uuid.UUID
    kind: Kind = "intake"


class InspectionUpdate(Schema):
    odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    summary: OptionalStr = Field(None, max_length=4000)


class ItemUpdate(Schema):
    result: Result | None = None
    notes: OptionalStr = Field(None, max_length=2000)


class AmendmentCreate(Schema):
    item_id: uuid.UUID
    result: Result
    notes: OptionalStr = Field(None, max_length=2000)
    reason: Reason


class PhotoRead(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    item_id: uuid.UUID | None
    caption: str | None
    created_at: datetime


class ItemRead(BaseModel):
    id: uuid.UUID
    section: str
    label: str
    guidance: str | None
    result: Result
    notes: str | None
    photos: list[PhotoRead]


class AmendmentRead(BaseModel):
    item_label: str
    old_result: Result
    new_result: Result
    old_notes: str | None
    new_notes: str | None
    reason: str
    amended_by: str
    amended_at: datetime


class InspectionSummary(BaseModel):
    id: uuid.UUID
    kind: Kind
    status: Literal["draft", "submitted"]
    template_name: str
    started_by: str | None
    submitted_at: datetime | None
    # Number of items per result: pass, attention, fail, not_inspected.
    counts: dict[Result, int]


class InspectionCapabilities(BaseModel):
    edit: bool
    amend: bool


class InspectionDetail(InspectionSummary):
    job_card: dict[str, str]
    vehicle: dict[str, str | int | None]
    customer_name: str
    branch_name: str
    organisation_name: str
    odometer_km: int | None
    summary: str | None
    submitted_by: str | None
    created_at: datetime
    items: list[ItemRead]
    general_photos: list[PhotoRead]
    amendments: list[AmendmentRead]
    capabilities: InspectionCapabilities
