import uuid
from typing import Literal

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, Paging, PortalCustomer
from app.schemas.appointment import (
    AppointmentRequestCreate,
    AppointmentRequestRead,
    ConfirmRequest,
    DeclineRequest,
)
from app.schemas.common import Page
from app.schemas.job_card import Ref
from app.services import appointment_requests

router = APIRouter(tags=["appointment requests"])


@router.get(
    "/appointment-requests",
    response_model=Page[AppointmentRequestRead],
    summary="Booking requests from customers",
    description="Pending first by preferred date. Filter by status; omit for pending.",
)
def list_requests(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    status: Literal["pending", "confirmed", "declined", "cancelled", "all"] = "pending",
    branch_id: uuid.UUID | None = None,
) -> Page[AppointmentRequestRead]:
    items, total = appointment_requests.list_requests(
        db, principal, paging, status=None if status == "all" else status, branch_id=branch_id
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/appointment-requests/{request_id}/confirm",
    response_model=AppointmentRequestRead,
    summary="Confirm a request into a booking",
    description="Books the appointment with the usual conflict checks and notifies the customer.",
)
def confirm(
    request_id: uuid.UUID, body: ConfirmRequest, principal: CurrentPrincipal, db: DbSession
) -> AppointmentRequestRead:
    return appointment_requests.confirm(db, principal, request_id, body)


@router.post(
    "/appointment-requests/{request_id}/decline",
    response_model=AppointmentRequestRead,
    summary="Decline a request",
)
def decline(
    request_id: uuid.UUID, body: DeclineRequest, principal: CurrentPrincipal, db: DbSession
) -> AppointmentRequestRead:
    return appointment_requests.decline(db, principal, request_id, body)


# --------------------------------------------------------------------------- portal

portal_router = APIRouter(prefix="/portal", tags=["customer portal"])


@portal_router.get("/branches", response_model=list[Ref], summary="Branches to book at")
def branches(who: PortalCustomer, db: DbSession) -> list[Ref]:
    return appointment_requests.portal_branches(db, who)


@portal_router.get(
    "/appointment-requests",
    response_model=list[AppointmentRequestRead],
    summary="My booking requests",
)
def my_requests(who: PortalCustomer, db: DbSession) -> list[AppointmentRequestRead]:
    return appointment_requests.portal_list(db, who)


@portal_router.post(
    "/appointment-requests",
    response_model=AppointmentRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request a booking",
)
def request_booking(
    body: AppointmentRequestCreate, who: PortalCustomer, db: DbSession
) -> AppointmentRequestRead:
    return appointment_requests.portal_create(db, who, body)


@portal_router.post(
    "/appointment-requests/{request_id}/cancel",
    response_model=AppointmentRequestRead,
    summary="Cancel a request that is still waiting",
)
def cancel_request(
    request_id: uuid.UUID, who: PortalCustomer, db: DbSession
) -> AppointmentRequestRead:
    return appointment_requests.portal_cancel(db, who, request_id)
