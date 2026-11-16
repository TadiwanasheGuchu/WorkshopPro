import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import OptionalStr, Schema, UpdateSchema
from app.schemas.job_card import FuelLevel, Priority, Ref, VehicleRef

Status = Literal["booked", "arrived", "cancelled", "no_show"]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Duration = Annotated[int, Field(ge=15, le=12 * 60, multiple_of=5)]


class AppointmentCreate(Schema):
    branch_id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID | None = None
    date: dt.date = Field(description="Local date in the organisation's time zone.")
    start_time: dt.time = Field(description="Local start time in the organisation's time zone.")
    duration_minutes: Duration = 60
    service_bay_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    reason: Reason
    notes: OptionalStr = Field(None, max_length=2000)


class AppointmentUpdate(UpdateSchema):
    non_nullable = frozenset({"date", "start_time", "duration_minutes", "reason"})

    vehicle_id: uuid.UUID | None = None
    date: dt.date | None = None
    start_time: dt.time | None = None
    duration_minutes: Duration | None = None
    service_bay_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    reason: Reason | None = None
    notes: OptionalStr = Field(None, max_length=2000)


class CancelRequest(Schema):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class CheckInRequest(Schema):
    intake_odometer_km: int | None = Field(None, ge=0, le=5_000_000)
    odometer_correction_reason: OptionalStr = Field(None, max_length=300)
    fuel_level: FuelLevel | None = None
    priority: Priority = "normal"
    complaint: OptionalStr = Field(
        None, max_length=4000, description="Defaults to the appointment reason."
    )


class AppointmentRead(BaseModel):
    id: uuid.UUID
    branch: Ref
    customer: Ref
    vehicle: VehicleRef | None
    service_bay: Ref | None
    assigned_user: Ref | None
    starts_at: dt.datetime
    ends_at: dt.datetime
    local_date: dt.date
    local_start: dt.time
    local_end: dt.time
    duration_minutes: int
    reason: str
    notes: str | None
    status: Status
    cancellation_reason: str | None
    job_card: Ref | None
    created_by: str | None


class DaySchedule(BaseModel):
    """One branch day, in the organisation's time zone."""

    date: dt.date
    timezone: str
    opens_at: dt.time | None
    closes_at: dt.time | None
    is_closed: bool
    bays: list[Ref]
    appointments: list[AppointmentRead]
