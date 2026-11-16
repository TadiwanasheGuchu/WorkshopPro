import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
    CancelRequest,
    CheckInRequest,
    DaySchedule,
)
from app.schemas.job_card import JobCardDetail, Ref
from app.services import appointments

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get(
    "/day",
    response_model=DaySchedule,
    summary="Branch schedule for one day",
    description="`date` is a local date in the organisation's time zone.",
)
def day_schedule(
    branch_id: uuid.UUID,
    day: Annotated[date, Query(alias="date")],
    principal: CurrentPrincipal,
    db: DbSession,
) -> DaySchedule:
    return appointments.day_schedule(db, principal, branch_id, day)


@router.get(
    "/bookable-users",
    response_model=list[Ref],
    summary="Mechanics who can be booked at a branch",
)
def bookable_users(branch_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[Ref]:
    return appointments.bookable_users(db, principal, branch_id)


@router.get(
    "/upcoming",
    response_model=list[AppointmentRead],
    summary="Upcoming bookings for a customer",
)
def upcoming(
    customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[AppointmentRead]:
    return appointments.upcoming_for_customer(db, principal, customer_id)


@router.post(
    "",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book an appointment",
    description=(
        "Date and time are local to the organisation's time zone. Overlapping bookings for "
        "the same bay or mechanic return 409 `scheduling_conflict`."
    ),
)
def create(body: AppointmentCreate, principal: CurrentPrincipal, db: DbSession) -> AppointmentRead:
    return appointments.create_appointment(db, principal, body)


@router.get("/{appointment_id}", response_model=AppointmentRead, summary="Appointment details")
def get(appointment_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> AppointmentRead:
    return appointments.get_appointment(db, principal, appointment_id)


@router.patch("/{appointment_id}", response_model=AppointmentRead, summary="Reschedule or edit")
def update(
    appointment_id: uuid.UUID, body: AppointmentUpdate, principal: CurrentPrincipal, db: DbSession
) -> AppointmentRead:
    return appointments.update_appointment(db, principal, appointment_id, body)


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead, summary="Cancel")
def cancel(
    appointment_id: uuid.UUID, body: CancelRequest, principal: CurrentPrincipal, db: DbSession
) -> AppointmentRead:
    return appointments.set_outcome(db, principal, appointment_id, "cancelled", body.reason)


@router.post("/{appointment_id}/no-show", response_model=AppointmentRead, summary="Mark no-show")
def no_show(
    appointment_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> AppointmentRead:
    return appointments.set_outcome(db, principal, appointment_id, "no_show")


@router.post(
    "/{appointment_id}/check-in",
    response_model=JobCardDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Check in (customer arrived)",
    description=(
        "Opens a job card from the appointment and links them. The booked mechanic is "
        "assigned when still eligible. Requires `job_cards.create` at the branch."
    ),
)
def check_in(
    appointment_id: uuid.UUID, body: CheckInRequest, principal: CurrentPrincipal, db: DbSession
) -> JobCardDetail:
    return appointments.check_in(db, principal, appointment_id, body)
