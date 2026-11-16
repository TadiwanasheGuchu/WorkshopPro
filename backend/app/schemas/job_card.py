import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

from app.schemas.common import OptionalStr, Schema, UpdateSchema
from app.schemas.inspection import InspectionSummary
from app.services.job_workflow import JobStatus

Priority = Literal["low", "normal", "high", "urgent"]
FuelLevel = Literal["empty", "quarter", "half", "three_quarters", "full"]
ExceptionType = Literal[
    "customer_verbal",
    "customer_written",
    "warranty",
    "internal_no_charge",
    "safety_emergency",
    "other",
]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class JobCardCreate(Schema):
    branch_id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    complaint: Text = Field(description="What the customer reports, in their words.")
    requested_work: OptionalStr = Field(None, max_length=4000)
    priority: Priority = "normal"
    intake_odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    odometer_correction_reason: OptionalStr = Field(None, max_length=300)
    fuel_level: FuelLevel | None = None
    promised_at: AwareDatetime | None = None
    service_bay_id: uuid.UUID | None = None


class JobCardUpdate(UpdateSchema):
    non_nullable = frozenset({"complaint", "priority", "version"})

    version: int = Field(description="The version you loaded; a stale version returns 409.")
    complaint: Text | None = None
    requested_work: OptionalStr = Field(None, max_length=4000)
    diagnosis: OptionalStr = Field(None, max_length=8000)
    work_performed: OptionalStr = Field(None, max_length=8000)
    priority: Priority | None = None
    fuel_level: FuelLevel | None = None
    promised_at: AwareDatetime | None = None
    service_bay_id: uuid.UUID | None = None


class TransitionRequest(Schema):
    to_status: JobStatus
    version: int
    note: OptionalStr = Field(None, max_length=1000)
    # Required when completing (vehicle handed over).
    collected_by_name: OptionalStr = Field(None, max_length=200)
    handover_notes: OptionalStr = Field(None, max_length=2000)
    # Required when cancelling.
    cancellation_reason: OptionalStr = Field(None, max_length=500)

    @model_validator(mode="after")
    def _required_fields(self) -> Self:
        if self.to_status == JobStatus.COMPLETED and not self.collected_by_name:
            raise ValueError("Record who collected the vehicle.")
        if self.to_status == JobStatus.CANCELLED and not self.cancellation_reason:
            raise ValueError("Give a reason for cancelling.")
        return self


class AssignmentRequest(Schema):
    user_id: uuid.UUID


class NoteCreate(Schema):
    body: Text
    visibility: Literal["internal", "customer"] = "internal"


class ExceptionCreate(Schema):
    exception_type: ExceptionType
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)]
    scope: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)
    ] = Field(description="Exactly which work is authorised, e.g. 'Replace front brake pads'.")
    customer_contact: OptionalStr = Field(
        None, max_length=200, description="Who at the customer agreed, and how they were reached."
    )
    max_amount: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)


class ExceptionRevoke(Schema):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


# --------------------------------------------------------------------------- reads


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class VehicleRef(BaseModel):
    id: uuid.UUID
    registration_number: str | None
    vin: str | None
    make: str
    model: str
    year: int | None


class JobCardSummary(BaseModel):
    id: uuid.UUID
    job_number: str
    status: JobStatus
    status_label: str
    priority: Priority
    branch: Ref
    customer: Ref
    vehicle: VehicleRef
    complaint: str
    received_at: datetime
    promised_at: datetime | None
    is_overdue: bool
    assignees: list[Ref]


class StatusChange(BaseModel):
    from_status: JobStatus | None
    to_status: JobStatus
    note: str | None
    changed_at: datetime
    changed_by: str | None


class NoteRead(BaseModel):
    id: uuid.UUID
    body: str
    visibility: Literal["internal", "customer"]
    author: str | None
    created_at: datetime


class ExceptionRead(BaseModel):
    id: uuid.UUID
    exception_type: ExceptionType
    reason: str
    scope: str
    customer_contact: str | None
    max_amount: Decimal | None
    currency_code: str
    authorised_by: str
    authorised_at: datetime
    revoked_at: datetime | None
    revoked_by: str | None
    revoke_reason: str | None


class AssignmentRead(BaseModel):
    user: Ref
    assigned_at: datetime
    assigned_by: str | None
    unassigned_at: datetime | None


class TransitionOption(BaseModel):
    to_status: JobStatus
    label: str
    allowed: bool
    reason: str | None = None


class Capabilities(BaseModel):
    """What the current user may do on this job (the API enforces the same rules)."""

    edit_details: bool
    edit_work: bool
    assign: bool
    add_notes: bool
    authorise_exception: bool
    transitions: list[TransitionOption]


class JobCardDetail(JobCardSummary):
    requested_work: str | None
    diagnosis: str | None
    work_performed: str | None
    intake_odometer_km: int | None
    fuel_level: FuelLevel | None
    service_bay: Ref | None
    received_by: str | None
    collected_at: datetime | None
    collected_by_name: str | None
    handover_notes: str | None
    cancellation_reason: str | None
    version: int
    approval_status: Literal[
        "not_required_yet", "quotation_approved", "exception_active", "missing"
    ]
    assignments: list[AssignmentRead]
    status_history: list[StatusChange]
    notes: list[NoteRead]
    approval_exceptions: list[ExceptionRead]
    inspections: list[InspectionSummary]
    capabilities: Capabilities


class AssignableUser(BaseModel):
    id: uuid.UUID
    full_name: str
    active_jobs: int


class JobSummaryCounts(BaseModel):
    """Counts for the dashboard. Times use the organisation's time zone."""

    by_status: dict[JobStatus, int]
    open_total: int
    overdue: int
    received_today: int
    my_assigned_open: int
