"""Appointment requests from the customer portal, and service reminders (CLAUDE.md §3.11,
§3.10).

- Customers request a date (morning, afternoon or any time) for one of their own vehicles
  at an active branch. Requests are scoped to the signed-in customer.
- Staff with appointments.manage confirm a request into a real booking (same rules as any
  booking: bay and mechanic conflicts, branch eligibility) or decline it with a reason.
  Confirming notifies the customer.
- Service reminders: a periodic job reminds customers ahead of a vehicle's next service
  due date. One reminder per vehicle and due date (unique row), so it never repeats.
"""

import logging
import uuid
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.time import utcnow
from app.db.session import get_sessionmaker
from app.models import (
    Appointment,
    AppointmentRequest,
    Branch,
    Customer,
    OrganisationSettings,
    ServiceReminder,
    User,
    Vehicle,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRequestCreate,
    AppointmentRequestRead,
    ConfirmRequest,
    DeclineRequest,
)
from app.schemas.common import PageParams
from app.schemas.job_card import Ref
from app.services import appointments, audit, notifications
from app.services.invoices import today as org_today
from app.services.portal import PortalPrincipal

logger = logging.getLogger(__name__)

MAX_DAYS_AHEAD = 180
MAX_PENDING_PER_CUSTOMER = 5


def _read(db: Session, r: AppointmentRequest) -> AppointmentRequestRead:
    branch = db.get_one(Branch, r.branch_id)
    customer = db.get_one(Customer, r.customer_id)
    vehicle = db.get(Vehicle, r.vehicle_id) if r.vehicle_id else None
    appt = db.get(Appointment, r.appointment_id) if r.appointment_id else None
    decided_by = (
        db.scalar(select(User.full_name).where(User.id == r.decided_by_user_id))
        if r.decided_by_user_id
        else None
    )
    return AppointmentRequestRead(
        id=r.id,
        status=r.status,  # type: ignore[arg-type]
        branch=Ref(id=branch.id, name=branch.name),
        customer=Ref(id=customer.id, name=customer.display_name),
        vehicle=Ref(id=vehicle.id, name=notifications.vehicle_label(vehicle)) if vehicle else None,
        preferred_date=r.preferred_date,
        time_of_day=r.time_of_day,  # type: ignore[arg-type]
        service_requested=r.service_requested,
        notes=r.notes,
        decline_reason=r.decline_reason,
        appointment_id=r.appointment_id,
        appointment_starts_at=appt.starts_at if appt else None,
        created_at=r.created_at,
        decided_by=decided_by,
        decided_at=r.decided_at,
    )


# --------------------------------------------------------------------------- portal


def portal_branches(db: Session, who: PortalPrincipal) -> list[Ref]:
    return [
        Ref(id=b.id, name=b.name)
        for b in db.scalars(
            select(Branch)
            .where(Branch.organisation_id == who.organisation_id, Branch.archived_at.is_(None))
            .order_by(Branch.name)
        )
    ]


def portal_list(db: Session, who: PortalPrincipal) -> list[AppointmentRequestRead]:
    rows = db.scalars(
        select(AppointmentRequest)
        .where(
            AppointmentRequest.organisation_id == who.organisation_id,
            AppointmentRequest.customer_id == who.customer_id,
        )
        .order_by(AppointmentRequest.created_at.desc())
        .limit(50)
    )
    return [_read(db, r) for r in rows]


def portal_create(
    db: Session, who: PortalPrincipal, body: AppointmentRequestCreate
) -> AppointmentRequestRead:
    branch = db.scalar(
        select(Branch).where(
            Branch.id == body.branch_id,
            Branch.organisation_id == who.organisation_id,
            Branch.archived_at.is_(None),
        )
    )
    if branch is None:
        raise NotFoundError("Branch not found.")
    if body.vehicle_id:
        vehicle = db.scalar(
            select(Vehicle).where(
                Vehicle.id == body.vehicle_id,
                Vehicle.organisation_id == who.organisation_id,
                Vehicle.customer_id == who.customer_id,
            )
        )
        if vehicle is None:
            raise NotFoundError("Vehicle not found.")
    today = org_today(db, who.organisation_id)
    if body.preferred_date < today:
        raise ConflictError("Choose today or a later date.")
    if body.preferred_date > today + timedelta(days=MAX_DAYS_AHEAD):
        raise ConflictError(f"Choose a date within the next {MAX_DAYS_AHEAD} days.")
    pending = db.scalar(
        select(AppointmentRequest.id)
        .where(
            AppointmentRequest.customer_id == who.customer_id,
            AppointmentRequest.status == "pending",
        )
        .offset(MAX_PENDING_PER_CUSTOMER - 1)
        .limit(1)
    )
    if pending:
        raise ConflictError(
            "You already have several requests waiting. The workshop will contact you."
        )
    r = AppointmentRequest(
        organisation_id=who.organisation_id,
        branch_id=branch.id,
        customer_id=who.customer_id,
        **body.model_dump(exclude={"branch_id"}),
    )
    db.add(r)
    db.flush()
    audit.record(
        db,
        organisation_id=who.organisation_id,
        branch_id=branch.id,
        actor_type="customer",
        action="appointment_request.created",
        entity_type="appointment_request",
        entity_id=r.id,
        summary=f"Booking requested in the portal for {body.preferred_date:%d/%m/%Y}: "
        f"{body.service_requested[:80]}",
    )
    db.commit()
    return _read(db, r)


def portal_cancel(
    db: Session, who: PortalPrincipal, request_id: uuid.UUID
) -> AppointmentRequestRead:
    r = db.scalar(
        select(AppointmentRequest)
        .where(
            AppointmentRequest.id == request_id,
            AppointmentRequest.organisation_id == who.organisation_id,
            AppointmentRequest.customer_id == who.customer_id,
        )
        .with_for_update()
    )
    if r is None:
        raise NotFoundError("Request not found.")
    if r.status != "pending":
        raise ConflictError("Only requests that are still waiting can be cancelled.")
    r.status = "cancelled"
    audit.record(
        db,
        organisation_id=who.organisation_id,
        branch_id=r.branch_id,
        actor_type="customer",
        action="appointment_request.cancelled",
        entity_type="appointment_request",
        entity_id=r.id,
        summary="Booking request cancelled by the customer",
    )
    db.commit()
    return _read(db, r)


# --------------------------------------------------------------------------- staff


def list_requests(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    status: str | None = "pending",
    branch_id: uuid.UUID | None = None,
) -> tuple[list[AppointmentRequestRead], int]:
    branches = principal.branch_ids_with(P.APPOINTMENTS_VIEW)
    if branches is not None and not branches:
        raise PermissionDeniedError("You do not have permission to view appointments.")
    conditions: list[Any] = [AppointmentRequest.organisation_id == principal.organisation_id]
    if branches is not None:
        conditions.append(AppointmentRequest.branch_id.in_(branches))
    if branch_id:
        conditions.append(AppointmentRequest.branch_id == branch_id)
    if status:
        conditions.append(AppointmentRequest.status == status)
    total = db.scalar(select(func.count()).select_from(AppointmentRequest).where(*conditions)) or 0
    rows = db.scalars(
        select(AppointmentRequest)
        .where(*conditions)
        .order_by(AppointmentRequest.preferred_date, AppointmentRequest.created_at)
        .limit(params.page_size)
        .offset(params.offset)
    )
    return [_read(db, r) for r in rows], total


def _staff_load(db: Session, principal: Principal, request_id: uuid.UUID) -> AppointmentRequest:
    r = db.scalar(
        select(AppointmentRequest)
        .where(
            AppointmentRequest.id == request_id,
            AppointmentRequest.organisation_id == principal.organisation_id,
        )
        .with_for_update()
    )
    if r is None or not principal.can(P.APPOINTMENTS_VIEW, r.branch_id):
        raise NotFoundError("Request not found.")
    principal.require(P.APPOINTMENTS_MANAGE, r.branch_id)
    if r.status != "pending":
        raise ConflictError("This request has already been handled.")
    return r


def confirm(
    db: Session, principal: Principal, request_id: uuid.UUID, body: ConfirmRequest
) -> AppointmentRequestRead:
    r = _staff_load(db, principal, request_id)
    appt = appointments.book(
        db,
        principal,
        AppointmentCreate(
            branch_id=r.branch_id,
            customer_id=r.customer_id,
            vehicle_id=r.vehicle_id,
            date=body.date,
            start_time=body.start_time,
            duration_minutes=body.duration_minutes,
            service_bay_id=body.service_bay_id,
            assigned_user_id=body.assigned_user_id,
            reason=r.service_requested,
            notes=body.notes or r.notes,
        ),
    )
    r.status, r.appointment_id = "confirmed", appt.id
    r.decided_by_user_id, r.decided_at = principal.user_id, utcnow()
    if body.notify_customer:
        tz = ZoneInfo(db.get_one(OrganisationSettings, r.organisation_id).timezone)
        local = appt.starts_at.astimezone(tz)
        vehicle = db.get(Vehicle, r.vehicle_id) if r.vehicle_id else None
        notifications.notify(
            db,
            organisation_id=r.organisation_id,
            branch_id=r.branch_id,
            customer_id=r.customer_id,
            event_name="appointment_confirmed",
            context={
                "vehicle": notifications.vehicle_label(vehicle) if vehicle else "your vehicle",
                "appointment_date": f"{local:%d/%m/%Y}",
                "appointment_time": f"{local:%H:%M}",
                "branch_name": db.get_one(Branch, r.branch_id).name,
            },
            related_type="appointment",
            related_id=appt.id,
            actor=principal,
        )
    audit.record(
        db,
        organisation_id=r.organisation_id,
        branch_id=r.branch_id,
        actor=principal,
        action="appointment_request.confirmed",
        entity_type="appointment_request",
        entity_id=r.id,
        summary="Booking request confirmed",
    )
    db.commit()
    return _read(db, r)


def decline(
    db: Session, principal: Principal, request_id: uuid.UUID, body: DeclineRequest
) -> AppointmentRequestRead:
    r = _staff_load(db, principal, request_id)
    r.status, r.decline_reason = "declined", body.reason
    r.decided_by_user_id, r.decided_at = principal.user_id, utcnow()
    audit.record(
        db,
        organisation_id=r.organisation_id,
        branch_id=r.branch_id,
        actor=principal,
        action="appointment_request.declined",
        entity_type="appointment_request",
        entity_id=r.id,
        summary=f"Booking request declined: {body.reason}",
    )
    db.commit()
    return _read(db, r)


# --------------------------------------------------------------------------- reminders


def send_service_reminders() -> int:
    """Periodic job. For every organisation, remind customers whose vehicle's next service
    is due within the configured number of days (or became due in the last 30 days and was
    never reminded). Safe to run repeatedly."""
    sent = 0
    with get_sessionmaker()() as db:
        orgs = list(
            db.execute(
                select(
                    OrganisationSettings.organisation_id, OrganisationSettings.service_reminder_days
                )
            )
        )
    for org_id, days in orgs:
        with get_sessionmaker()() as db:
            today = org_today(db, org_id)
            due = list(
                db.scalars(
                    select(Vehicle)
                    .join(Customer, Customer.id == Vehicle.customer_id)
                    .where(
                        Vehicle.organisation_id == org_id,
                        Vehicle.archived_at.is_(None),
                        Customer.archived_at.is_(None),
                        Vehicle.next_service_due_date.is_not(None),
                        Vehicle.next_service_due_date <= today + timedelta(days=days),
                        Vehicle.next_service_due_date >= today - timedelta(days=30),
                        ~select(ServiceReminder.id)
                        .where(
                            ServiceReminder.vehicle_id == Vehicle.id,
                            ServiceReminder.due_date == Vehicle.next_service_due_date,
                        )
                        .exists(),
                    )
                )
            )
            for vehicle in due:
                try:
                    reminder = ServiceReminder(
                        organisation_id=org_id,
                        vehicle_id=vehicle.id,
                        due_date=vehicle.next_service_due_date,
                    )
                    db.add(reminder)
                    db.flush()  # the unique row is the guard against double sending
                    n = notifications.notify(
                        db,
                        organisation_id=org_id,
                        branch_id=None,
                        customer_id=vehicle.customer_id,
                        event_name="service_reminder",
                        context={
                            "vehicle": notifications.vehicle_label(vehicle),
                            "service_due_date": f"{vehicle.next_service_due_date:%d/%m/%Y}",
                        },
                        related_type="vehicle",
                        related_id=vehicle.id,
                    )
                    reminder.notification_id = n.id if n else None
                    db.commit()
                    sent += 1
                except IntegrityError:
                    db.rollback()
    return sent


def upcoming_for_portal(db: Session, who: PortalPrincipal) -> list[AppointmentRequestRead]:
    """Pending and confirmed requests whose booking is still ahead."""
    now = utcnow()
    rows = db.scalars(
        select(AppointmentRequest)
        .outerjoin(Appointment, Appointment.id == AppointmentRequest.appointment_id)
        .where(
            AppointmentRequest.customer_id == who.customer_id,
            AppointmentRequest.organisation_id == who.organisation_id,
            or_(
                AppointmentRequest.status == "pending",
                (AppointmentRequest.status == "confirmed") & (Appointment.starts_at >= now),
            ),
        )
        .order_by(AppointmentRequest.preferred_date)
    )
    return [_read(db, r) for r in rows]
