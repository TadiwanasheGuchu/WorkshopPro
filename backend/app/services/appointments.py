"""Appointments: manual booking per branch, bay and mechanic (CLAUDE.md §3.12).

Times are entered and displayed in the organisation's time zone and stored as UTC.
Overlapping bookings for the same bay or mechanic are rejected.
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import (
    Appointment,
    Branch,
    BranchOperatingHours,
    Customer,
    JobCard,
    OrganisationSettings,
    ServiceBay,
    User,
    Vehicle,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal, load_principal
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
    CheckInRequest,
    DaySchedule,
)
from app.schemas.job_card import JobCardCreate, JobCardDetail, Ref, VehicleRef
from app.services import audit, job_cards
from app.services.common import get_scoped


class SchedulingConflictError(ConflictError):
    code = "scheduling_conflict"


def _tz(db: Session, organisation_id: uuid.UUID) -> ZoneInfo:
    name = db.scalar(
        select(OrganisationSettings.timezone).where(
            OrganisationSettings.organisation_id == organisation_id
        )
    )
    return ZoneInfo(name or "UTC")


def _to_read(db: Session, appts: list[Appointment], tz: ZoneInfo) -> list[AppointmentRead]:
    if not appts:
        return []

    def lookup(model: Any, ids: set[Any], label: Any) -> dict[Any, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        return dict(db.execute(select(model.id, label).where(model.id.in_(ids))).all())

    branches = lookup(Branch, {a.branch_id for a in appts}, Branch.name)
    customers = lookup(Customer, {a.customer_id for a in appts}, Customer.display_name)
    bays = lookup(ServiceBay, {a.service_bay_id for a in appts}, ServiceBay.name)
    users = lookup(
        User,
        {a.assigned_user_id for a in appts} | {a.created_by_user_id for a in appts},
        User.full_name,
    )
    jobs = lookup(JobCard, {a.job_card_id for a in appts}, JobCard.job_number)
    vehicle_ids = {a.vehicle_id for a in appts if a.vehicle_id}
    vehicles = (
        {v.id: v for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(vehicle_ids)))}
        if vehicle_ids
        else {}
    )
    result = []
    for a in appts:
        v = vehicles.get(a.vehicle_id) if a.vehicle_id else None
        start, end = a.starts_at.astimezone(tz), a.ends_at.astimezone(tz)
        result.append(
            AppointmentRead(
                id=a.id,
                branch=Ref(id=a.branch_id, name=branches.get(a.branch_id, "")),
                customer=Ref(id=a.customer_id, name=customers.get(a.customer_id, "")),
                vehicle=VehicleRef(
                    id=v.id,
                    registration_number=v.registration_number,
                    vin=v.vin,
                    make=v.make,
                    model=v.model,
                    year=v.year,
                )
                if v
                else None,
                service_bay=Ref(id=a.service_bay_id, name=bays[a.service_bay_id])
                if a.service_bay_id
                else None,
                assigned_user=Ref(id=a.assigned_user_id, name=users[a.assigned_user_id])
                if a.assigned_user_id
                else None,
                starts_at=a.starts_at,
                ends_at=a.ends_at,
                local_date=start.date(),
                local_start=start.time().replace(tzinfo=None),
                local_end=end.time().replace(tzinfo=None),
                duration_minutes=int((a.ends_at - a.starts_at).total_seconds() // 60),
                reason=a.reason,
                notes=a.notes,
                status=a.status,  # type: ignore[arg-type]
                cancellation_reason=a.cancellation_reason,
                job_card=Ref(id=a.job_card_id, name=jobs.get(a.job_card_id, ""))
                if a.job_card_id
                else None,
                created_by=users.get(a.created_by_user_id) if a.created_by_user_id else None,
            )
        )
    return result


def _get(
    db: Session, principal: Principal, appointment_id: uuid.UUID, permission: str
) -> Appointment:
    appt = get_scoped(db, Appointment, appointment_id, principal.organisation_id)
    if not principal.can(permission, appt.branch_id):
        # Hide appointments at branches the caller cannot see.
        if not principal.can(P.APPOINTMENTS_VIEW, appt.branch_id):
            raise NotFoundError("Appointment not found.")
        principal.require(permission, appt.branch_id)
    return appt


def _validate_refs(
    db: Session,
    principal: Principal,
    branch_id: uuid.UUID,
    customer_id: uuid.UUID,
    vehicle_id: uuid.UUID | None,
    bay_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> None:
    branch = get_scoped(db, Branch, branch_id, principal.organisation_id)
    if branch.archived_at is not None:
        raise ConflictError("This branch is archived.")
    customer = get_scoped(db, Customer, customer_id, principal.organisation_id)
    if customer.archived_at is not None:
        raise ConflictError("This customer is archived.")
    if vehicle_id:
        vehicle = get_scoped(db, Vehicle, vehicle_id, principal.organisation_id)
        if vehicle.customer_id != customer.id or vehicle.archived_at is not None:
            raise ConflictError("Choose an active vehicle that belongs to this customer.")
    if bay_id:
        bay = get_scoped(db, ServiceBay, bay_id, principal.organisation_id)
        if bay.branch_id != branch.id or not bay.is_active:
            raise ConflictError("Choose an active service bay at this branch.")
    if user_id:
        user = db.scalar(
            select(User).where(
                User.id == user_id, User.organisation_id == principal.organisation_id
            )
        )
        if user is None:
            raise NotFoundError("User not found.")
        if not user.is_active or not load_principal(db, user, None).can(
            P.JOB_CARDS_WORK, branch.id
        ):
            raise ConflictError(f"{user.full_name} cannot be booked for work at this branch.")


def _check_conflicts(
    db: Session,
    appt_id: uuid.UUID | None,
    starts_at: datetime,
    ends_at: datetime,
    bay_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> None:
    clauses = []
    if bay_id:
        clauses.append(Appointment.service_bay_id == bay_id)
    if user_id:
        clauses.append(Appointment.assigned_user_id == user_id)
    if not clauses:
        return
    stmt = select(Appointment).where(
        or_(*clauses),
        Appointment.status == "booked",
        Appointment.starts_at < ends_at,
        Appointment.ends_at > starts_at,
    )
    if appt_id:
        stmt = stmt.where(Appointment.id != appt_id)
    clash = db.scalar(stmt.with_for_update().limit(1))
    if clash:
        what = "service bay" if bay_id and clash.service_bay_id == bay_id else "mechanic"
        raise SchedulingConflictError(
            f"The {what} is already booked at that time.",
            details={"appointment_id": str(clash.id), "conflict": what},
        )


def _window(tz: ZoneInfo, day: date, start: time, minutes: int) -> tuple[datetime, datetime]:
    starts_at = datetime.combine(day, start, tzinfo=tz)
    return starts_at, starts_at + timedelta(minutes=minutes)


# --------------------------------------------------------------------------- reads


def day_schedule(db: Session, principal: Principal, branch_id: uuid.UUID, day: date) -> DaySchedule:
    principal.require(P.APPOINTMENTS_VIEW, branch_id)
    branch = get_scoped(db, Branch, branch_id, principal.organisation_id)
    tz = _tz(db, principal.organisation_id)
    start = datetime.combine(day, time.min, tzinfo=tz)
    appts = list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.organisation_id == principal.organisation_id,
                Appointment.branch_id == branch.id,
                Appointment.starts_at >= start,
                Appointment.starts_at < start + timedelta(days=1),
            )
            .order_by(Appointment.starts_at, Appointment.id)
        )
    )
    hours = db.scalar(
        select(BranchOperatingHours).where(
            BranchOperatingHours.branch_id == branch.id,
            BranchOperatingHours.weekday == day.weekday(),
        )
    )
    bays = db.scalars(
        select(ServiceBay)
        .where(ServiceBay.branch_id == branch.id, ServiceBay.is_active)
        .order_by(ServiceBay.name)
    )
    return DaySchedule(
        date=day,
        timezone=str(tz),
        opens_at=hours.opens_at if hours else None,
        closes_at=hours.closes_at if hours else None,
        is_closed=hours.is_closed if hours else False,
        bays=[Ref(id=b.id, name=b.name) for b in bays],
        appointments=_to_read(db, appts, tz),
    )


def get_appointment(
    db: Session, principal: Principal, appointment_id: uuid.UUID
) -> AppointmentRead:
    appt = _get(db, principal, appointment_id, P.APPOINTMENTS_VIEW)
    return _to_read(db, [appt], _tz(db, principal.organisation_id))[0]


def upcoming_for_customer(
    db: Session, principal: Principal, customer_id: uuid.UUID
) -> list[AppointmentRead]:
    get_scoped(db, Customer, customer_id, principal.organisation_id)
    branches = principal.branch_ids_with(P.APPOINTMENTS_VIEW)
    stmt = select(Appointment).where(
        Appointment.customer_id == customer_id,
        Appointment.status == "booked",
        Appointment.ends_at >= utcnow(),
    )
    if branches is not None:
        stmt = stmt.where(Appointment.branch_id.in_(branches))
    appts = list(db.scalars(stmt.order_by(Appointment.starts_at).limit(20)))
    return _to_read(db, appts, _tz(db, principal.organisation_id))


# --------------------------------------------------------------------------- writes


def create_appointment(
    db: Session, principal: Principal, body: AppointmentCreate
) -> AppointmentRead:
    principal.require(P.APPOINTMENTS_MANAGE, body.branch_id)
    _validate_refs(
        db,
        principal,
        body.branch_id,
        body.customer_id,
        body.vehicle_id,
        body.service_bay_id,
        body.assigned_user_id,
    )
    tz = _tz(db, principal.organisation_id)
    starts_at, ends_at = _window(tz, body.date, body.start_time, body.duration_minutes)
    _check_conflicts(db, None, starts_at, ends_at, body.service_bay_id, body.assigned_user_id)
    appt = Appointment(
        organisation_id=principal.organisation_id,
        branch_id=body.branch_id,
        customer_id=body.customer_id,
        vehicle_id=body.vehicle_id,
        service_bay_id=body.service_bay_id,
        assigned_user_id=body.assigned_user_id,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=body.reason,
        notes=body.notes,
        status="booked",
        created_by_user_id=principal.user_id,
    )
    db.add(appt)
    db.flush()
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=body.branch_id,
        actor=principal,
        action="appointment.booked",
        entity_type="appointment",
        entity_id=appt.id,
        summary=f"Appointment booked for {starts_at.astimezone(tz):%d/%m/%Y %H:%M}: "
        f"{body.reason[:80]}",
    )
    db.commit()
    return _to_read(db, [appt], tz)[0]


def update_appointment(
    db: Session, principal: Principal, appointment_id: uuid.UUID, body: AppointmentUpdate
) -> AppointmentRead:
    appt = _get(db, principal, appointment_id, P.APPOINTMENTS_MANAGE)
    if appt.status != "booked":
        raise ConflictError("Only booked appointments can be changed.")
    tz = _tz(db, principal.organisation_id)
    data = body.changes()
    local_start = appt.starts_at.astimezone(tz)
    day = data.pop("date", local_start.date())
    start = data.pop("start_time", local_start.time().replace(tzinfo=None))
    minutes = data.pop(
        "duration_minutes", int((appt.ends_at - appt.starts_at).total_seconds() // 60)
    )
    for key, value in data.items():
        setattr(appt, key, value)
    _validate_refs(
        db,
        principal,
        appt.branch_id,
        appt.customer_id,
        appt.vehicle_id,
        appt.service_bay_id,
        appt.assigned_user_id,
    )
    appt.starts_at, appt.ends_at = _window(tz, day, start, minutes)
    _check_conflicts(
        db, appt.id, appt.starts_at, appt.ends_at, appt.service_bay_id, appt.assigned_user_id
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=appt.branch_id,
        actor=principal,
        action="appointment.updated",
        entity_type="appointment",
        entity_id=appt.id,
        summary=f"Appointment moved/updated to {appt.starts_at.astimezone(tz):%d/%m/%Y %H:%M}",
    )
    db.commit()
    return _to_read(db, [appt], tz)[0]


def set_outcome(
    db: Session,
    principal: Principal,
    appointment_id: uuid.UUID,
    status: str,
    reason: str | None = None,
) -> AppointmentRead:
    """Cancel or mark as no-show."""
    appt = _get(db, principal, appointment_id, P.APPOINTMENTS_MANAGE)
    if appt.status != "booked":
        raise ConflictError("This appointment is no longer open.")
    appt.status = status
    appt.cancellation_reason = reason
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=appt.branch_id,
        actor=principal,
        action=f"appointment.{status}",
        entity_type="appointment",
        entity_id=appt.id,
        summary=f"Appointment {'cancelled' if status == 'cancelled' else 'marked no-show'}",
        changes={"reason": reason} if reason else None,
    )
    db.commit()
    return _to_read(db, [appt], _tz(db, principal.organisation_id))[0]


def check_in(
    db: Session, principal: Principal, appointment_id: uuid.UUID, body: CheckInRequest
) -> JobCardDetail:
    """The customer has arrived: open a job card from the booking and link it."""
    appt = _get(db, principal, appointment_id, P.APPOINTMENTS_MANAGE)
    if appt.status != "booked":
        raise ConflictError("This appointment is no longer open.")
    if appt.vehicle_id is None:
        raise ConflictError("Add the vehicle to the appointment before checking in.")
    job = job_cards.create_job_card(
        db,
        principal,
        JobCardCreate(
            branch_id=appt.branch_id,
            customer_id=appt.customer_id,
            vehicle_id=appt.vehicle_id,
            complaint=body.complaint or appt.reason,
            requested_work=appt.notes,
            priority=body.priority,
            intake_odometer_km=body.intake_odometer_km,
            odometer_correction_reason=body.odometer_correction_reason,
            fuel_level=body.fuel_level,
            service_bay_id=appt.service_bay_id,
        ),
    )
    appt = db.get_one(Appointment, appt.id)
    appt.status = "arrived"
    appt.job_card_id = job.id
    if appt.assigned_user_id:
        try:
            job = job_cards.assign(db, principal, job.id, appt.assigned_user_id)
        except AppError:
            # Assignment is a convenience (e.g. the mechanic has since lost access);
            # the job card is already open, so keep it and leave it unassigned.
            db.rollback()
            appt = db.get_one(Appointment, appt.id)
            appt.status, appt.job_card_id = "arrived", job.id
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=appt.branch_id,
        actor=principal,
        action="appointment.arrived",
        entity_type="appointment",
        entity_id=appt.id,
        summary=f"Customer arrived; job {job.job_number} opened from appointment",
    )
    db.commit()
    return job_cards.get_job_card(db, principal, job.id)


def bookable_users(db: Session, principal: Principal, branch_id: uuid.UUID) -> list[Ref]:
    principal.require(P.APPOINTMENTS_VIEW, branch_id)
    get_scoped(db, Branch, branch_id, principal.organisation_id)
    return [
        Ref(id=u.id, name=u.full_name)
        for u in job_cards.workers_for_branch(db, principal.organisation_id, branch_id)
    ]
