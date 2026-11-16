"""Job cards: intake, workflow transitions, assignments, notes and approval exceptions.

Visibility:
- job_cards.view in a branch: every job card in that branch.
- job_cards.work in a branch: only job cards the user is currently assigned to.
Records outside the caller's visibility are reported as not found.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, exists, false, func, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    AppError,
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.time import utcnow
from app.models import (
    Branch,
    Customer,
    JobApprovalException,
    JobAssignment,
    JobCard,
    JobNote,
    JobStatusHistory,
    OrganisationSettings,
    Quotation,
    QuotationVersion,
    ServiceBay,
    User,
    Vehicle,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal, load_principal
from app.schemas.common import PageParams
from app.schemas.customer import registration_key
from app.schemas.job_card import (
    AssignableUser,
    AssignmentRead,
    Capabilities,
    ExceptionCreate,
    ExceptionRead,
    JobCardCreate,
    JobCardDetail,
    JobCardSummary,
    JobCardUpdate,
    JobSummaryCounts,
    NoteCreate,
    NoteRead,
    Ref,
    StatusChange,
    TransitionOption,
    TransitionRequest,
    VehicleRef,
)
from app.services import audit, inspection_summary, numbering
from app.services.common import get_scoped
from app.services.job_workflow import (
    LABELS,
    MECHANIC_TRANSITIONS,
    TERMINAL,
    TRANSITIONS,
    JobStatus,
    is_valid,
    needs_approval,
)
from app.services.vehicles import OdometerDecreaseError


class ApprovalRequiredError(AppError):
    status_code = 409
    code = "approval_required"


class StaleVersionError(AppError):
    status_code = 409
    code = "stale_version"


_PRIORITY_RANK = case(
    {"urgent": 0, "high": 1, "normal": 2, "low": 3}, value=JobCard.priority, else_=4
)
_OPEN = [s.value for s in JobStatus if s not in TERMINAL]
_WORK_FIELDS = frozenset({"diagnosis", "work_performed"})


# --------------------------------------------------------------------------- visibility


def _visibility(principal: Principal) -> Any:
    """SQL condition restricting job cards to those the caller may see."""
    view = principal.branch_ids_with(P.JOB_CARDS_VIEW)
    if view is None:
        return true()
    conditions = []
    if view:
        conditions.append(JobCard.branch_id.in_(view))
    work = principal.branch_ids_with(P.JOB_CARDS_WORK)
    assigned = exists(
        select(JobAssignment.id).where(
            JobAssignment.job_card_id == JobCard.id,
            JobAssignment.user_id == principal.user_id,
            JobAssignment.unassigned_at.is_(None),
        )
    )
    if work is None:
        conditions.append(assigned)
    elif work:
        conditions.append(and_(JobCard.branch_id.in_(work), assigned))
    return or_(*conditions) if conditions else false()


def _require_any_access(principal: Principal) -> None:
    if not (
        principal.can_in_any_branch(P.JOB_CARDS_VIEW)
        or principal.can_in_any_branch(P.JOB_CARDS_WORK)
    ):
        raise PermissionDeniedError("You do not have permission to view job cards.")


def _is_assigned(db: Session, job_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(JobAssignment.id).where(
                JobAssignment.job_card_id == job_id,
                JobAssignment.user_id == user_id,
                JobAssignment.unassigned_at.is_(None),
            )
        )
    )


def get_visible_job_card(
    db: Session, principal: Principal, job_id: uuid.UUID, *, lock: bool = False
) -> JobCard:
    _require_any_access(principal)
    stmt = select(JobCard).where(
        JobCard.id == job_id,
        JobCard.organisation_id == principal.organisation_id,
        _visibility(principal),
    )
    if lock:
        stmt = stmt.with_for_update(of=JobCard)
    job = db.scalar(stmt)
    if job is None:
        raise NotFoundError("Job card not found.")
    return job


def _check_version(job: JobCard, version: int) -> None:
    if job.version != version:
        raise StaleVersionError(
            "This job card was changed by someone else. Reload it and try again.",
            details={"current_version": job.version},
        )


def _require_open(job: JobCard) -> None:
    if JobStatus(job.status) in TERMINAL:
        raise ConflictError(f"Job {job.job_number} is {LABELS[JobStatus(job.status)].lower()}.")


def has_approved_quotation(db: Session, job_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(QuotationVersion.id)
            .join(Quotation, Quotation.id == QuotationVersion.quotation_id)
            .where(Quotation.job_card_id == job_id, QuotationVersion.status == "approved")
        )
    )


def _has_customer_approval(db: Session, job_id: uuid.UUID) -> bool:
    """Approved current quotation, or an active authorised exception (CLAUDE.md §3.4)."""
    return has_approved_quotation(db, job_id) or _has_active_exception(db, job_id)


def _has_active_exception(db: Session, job_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(JobApprovalException.id).where(
                JobApprovalException.job_card_id == job_id,
                JobApprovalException.revoked_at.is_(None),
            )
        )
    )


def _can_transition(principal: Principal, job: JobCard, assigned: bool, target: JobStatus) -> bool:
    if principal.can(P.JOB_CARDS_MANAGE, job.branch_id):
        return True
    return (
        assigned
        and principal.can(P.JOB_CARDS_WORK, job.branch_id)
        and (JobStatus(job.status), target) in MECHANIC_TRANSITIONS
    )


# --------------------------------------------------------------------------- reads


def _names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all())


def _is_overdue(job: JobCard, now: datetime) -> bool:
    return bool(job.promised_at and job.promised_at < now and JobStatus(job.status) not in TERMINAL)


def _summaries(db: Session, jobs: list[JobCard]) -> list[JobCardSummary]:
    if not jobs:
        return []
    now = utcnow()
    branches = dict(
        db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_({j.branch_id for j in jobs}))
        ).all()
    )
    customers = dict(
        db.execute(
            select(Customer.id, Customer.display_name).where(
                Customer.id.in_({j.customer_id for j in jobs})
            )
        ).all()
    )
    vehicles = {
        v.id: v
        for v in db.scalars(select(Vehicle).where(Vehicle.id.in_({j.vehicle_id for j in jobs})))
    }
    assignees: dict[uuid.UUID, list[Ref]] = {j.id: [] for j in jobs}
    for job_id, user_id, name in db.execute(
        select(JobAssignment.job_card_id, User.id, User.full_name)
        .join(User, User.id == JobAssignment.user_id)
        .where(
            JobAssignment.job_card_id.in_(assignees.keys()), JobAssignment.unassigned_at.is_(None)
        )
        .order_by(JobAssignment.assigned_at)
    ):
        assignees[job_id].append(Ref(id=user_id, name=name))

    result = []
    for j in jobs:
        v = vehicles[j.vehicle_id]
        result.append(
            JobCardSummary(
                id=j.id,
                job_number=j.job_number,
                status=JobStatus(j.status),
                status_label=LABELS[JobStatus(j.status)],
                priority=j.priority,  # type: ignore[arg-type]
                branch=Ref(id=j.branch_id, name=branches[j.branch_id]),
                customer=Ref(id=j.customer_id, name=customers[j.customer_id]),
                vehicle=VehicleRef(
                    id=v.id,
                    registration_number=v.registration_number,
                    vin=v.vin,
                    make=v.make,
                    model=v.model,
                    year=v.year,
                ),
                complaint=j.complaint,
                received_at=j.received_at,
                promised_at=j.promised_at,
                is_overdue=_is_overdue(j, now),
                assignees=assignees[j.id],
            )
        )
    return result


def list_job_cards(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    branch_id: uuid.UUID | None = None,
    statuses: list[JobStatus] | None = None,
    open_only: bool = False,
    assigned_to_me: bool = False,
    overdue: bool = False,
    vehicle_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[JobCardSummary], int]:
    _require_any_access(principal)
    conditions: list[Any] = [
        JobCard.organisation_id == principal.organisation_id,
        _visibility(principal),
    ]
    if branch_id:
        conditions.append(JobCard.branch_id == branch_id)
    if statuses:
        conditions.append(JobCard.status.in_([s.value for s in statuses]))
    if open_only or overdue:
        conditions.append(JobCard.status.in_(_OPEN))
    if overdue:
        conditions.append(JobCard.promised_at < utcnow())
    if vehicle_id:
        conditions.append(JobCard.vehicle_id == vehicle_id)
    if customer_id:
        conditions.append(JobCard.customer_id == customer_id)
    if assigned_to_me:
        conditions.append(
            exists(
                select(JobAssignment.id).where(
                    JobAssignment.job_card_id == JobCard.id,
                    JobAssignment.user_id == principal.user_id,
                    JobAssignment.unassigned_at.is_(None),
                )
            )
        )
    if search:
        term = search.strip()
        key = registration_key(term)
        conditions.append(
            or_(
                JobCard.job_number.ilike(f"%{term}%"),
                exists(
                    select(Customer.id).where(
                        Customer.id == JobCard.customer_id,
                        Customer.display_name.ilike(f"%{term}%"),
                    )
                ),
                *(
                    [
                        exists(
                            select(Vehicle.id).where(
                                Vehicle.id == JobCard.vehicle_id,
                                or_(
                                    Vehicle.registration_key.contains(key),
                                    Vehicle.vin.contains(key),
                                ),
                            )
                        )
                    ]
                    if key
                    else []
                ),
            )
        )

    total = db.scalar(select(func.count()).select_from(JobCard).where(*conditions)) or 0
    jobs = list(
        db.scalars(
            select(JobCard)
            .where(*conditions)
            .order_by(
                case((JobCard.status.in_(_OPEN), 0), else_=1),
                _PRIORITY_RANK,
                JobCard.promised_at.asc().nulls_last(),
                JobCard.received_at.desc(),
            )
            .limit(params.page_size)
            .offset(params.offset)
        )
    )
    return _summaries(db, jobs), total


def _capabilities(db: Session, principal: Principal, job: JobCard, assigned: bool) -> Capabilities:
    current = JobStatus(job.status)
    is_open = current not in TERMINAL
    manage = principal.can(P.JOB_CARDS_MANAGE, job.branch_id)
    work = assigned and principal.can(P.JOB_CARDS_WORK, job.branch_id)
    has_exception = _has_customer_approval(db, job.id)
    options = []
    for target in sorted(TRANSITIONS[current], key=list(JobStatus).index):
        if not _can_transition(principal, job, assigned, target):
            continue
        blocked = needs_approval(current, target) and not has_exception
        options.append(
            TransitionOption(
                to_status=target,
                label=LABELS[target],
                allowed=not blocked,
                reason="Needs an approved quotation or an authorised exception."
                if blocked
                else None,
            )
        )
    return Capabilities(
        edit_details=is_open and manage,
        edit_work=is_open and (manage or work),
        assign=is_open and principal.can(P.JOB_CARDS_ASSIGN, job.branch_id),
        add_notes=manage or work or principal.can(P.JOB_CARDS_CREATE, job.branch_id),
        authorise_exception=is_open
        and principal.can(P.JOB_CARDS_AUTHORISE_EXCEPTION, job.branch_id),
        transitions=options,
    )


def get_job_card(db: Session, principal: Principal, job_id: uuid.UUID) -> JobCardDetail:
    job = get_visible_job_card(db, principal, job_id)
    summary = _summaries(db, [job])[0]

    history = list(
        db.scalars(
            select(JobStatusHistory)
            .where(JobStatusHistory.job_card_id == job.id)
            .order_by(JobStatusHistory.changed_at, JobStatusHistory.id)
        )
    )
    notes = list(
        db.scalars(
            select(JobNote).where(JobNote.job_card_id == job.id).order_by(JobNote.created_at)
        )
    )
    exceptions = list(
        db.scalars(
            select(JobApprovalException)
            .where(JobApprovalException.job_card_id == job.id)
            .order_by(JobApprovalException.authorised_at)
        )
    )
    assignments = list(
        db.scalars(
            select(JobAssignment)
            .where(JobAssignment.job_card_id == job.id)
            .order_by(JobAssignment.assigned_at)
        )
    )
    names = _names(
        db,
        [job.received_by_user_id]
        + [h.changed_by_user_id for h in history]
        + [n.author_user_id for n in notes]
        + [e.authorised_by_user_id for e in exceptions]
        + [e.revoked_by_user_id for e in exceptions]
        + [a.user_id for a in assignments]
        + [a.assigned_by_user_id for a in assignments],
    )
    bay = db.get(ServiceBay, job.service_bay_id) if job.service_bay_id else None
    assigned = any(a.user_id == principal.user_id and a.unassigned_at is None for a in assignments)
    active_exception = any(e.revoked_at is None for e in exceptions)
    current = JobStatus(job.status)
    approval = (
        "quotation_approved"
        if has_approved_quotation(db, job.id)
        else "exception_active"
        if active_exception
        else "not_required_yet"
        if current
        in {
            JobStatus.VEHICLE_RECEIVED,
            JobStatus.INSPECTION_PENDING,
            JobStatus.DIAGNOSIS_IN_PROGRESS,
            JobStatus.AWAITING_APPROVAL,
            JobStatus.CANCELLED,
        }
        else "missing"
    )

    return JobCardDetail(
        **summary.model_dump(),
        requested_work=job.requested_work,
        diagnosis=job.diagnosis,
        work_performed=job.work_performed,
        intake_odometer_km=job.intake_odometer_km,
        fuel_level=job.fuel_level,  # type: ignore[arg-type]
        service_bay=Ref(id=bay.id, name=bay.name) if bay else None,
        received_by=names.get(job.received_by_user_id) if job.received_by_user_id else None,
        collected_at=job.collected_at,
        collected_by_name=job.collected_by_name,
        handover_notes=job.handover_notes,
        cancellation_reason=job.cancellation_reason,
        version=job.version,
        approval_status=approval,  # type: ignore[arg-type]
        assignments=[
            AssignmentRead(
                user=Ref(id=a.user_id, name=names.get(a.user_id, "")),
                assigned_at=a.assigned_at,
                assigned_by=names.get(a.assigned_by_user_id) if a.assigned_by_user_id else None,
                unassigned_at=a.unassigned_at,
            )
            for a in assignments
        ],
        status_history=[
            StatusChange(
                from_status=JobStatus(h.from_status) if h.from_status else None,
                to_status=JobStatus(h.to_status),
                note=h.note,
                changed_at=h.changed_at,
                changed_by=names.get(h.changed_by_user_id) if h.changed_by_user_id else None,
            )
            for h in history
        ],
        notes=[
            NoteRead(
                id=n.id,
                body=n.body,
                visibility=n.visibility,  # type: ignore[arg-type]
                author=names.get(n.author_user_id) if n.author_user_id else None,
                created_at=n.created_at,
            )
            for n in notes
        ],
        approval_exceptions=[
            ExceptionRead(
                id=e.id,
                exception_type=e.exception_type,  # type: ignore[arg-type]
                reason=e.reason,
                scope=e.scope,
                customer_contact=e.customer_contact,
                max_amount=e.max_amount,
                currency_code=e.currency_code,
                authorised_by=names.get(e.authorised_by_user_id, ""),
                authorised_at=e.authorised_at,
                revoked_at=e.revoked_at,
                revoked_by=names.get(e.revoked_by_user_id) if e.revoked_by_user_id else None,
                revoke_reason=e.revoke_reason,
            )
            for e in exceptions
        ],
        inspections=inspection_summary.summaries_for_job(db, job.id),
        capabilities=_capabilities(db, principal, job, assigned),
    )


def summary_counts(
    db: Session, principal: Principal, *, branch_id: uuid.UUID | None = None
) -> JobSummaryCounts:
    _require_any_access(principal)
    conditions: list[Any] = [
        JobCard.organisation_id == principal.organisation_id,
        _visibility(principal),
    ]
    if branch_id:
        conditions.append(JobCard.branch_id == branch_id)
    now = utcnow()
    tz = ZoneInfo(
        db.scalar(
            select(OrganisationSettings.timezone).where(
                OrganisationSettings.organisation_id == principal.organisation_id
            )
        )
        or "UTC"
    )
    start_of_day = datetime.combine(now.astimezone(tz).date(), time.min, tzinfo=tz)

    by_status = {
        JobStatus(s): n
        for s, n in db.execute(
            select(JobCard.status, func.count()).where(*conditions).group_by(JobCard.status)
        )
    }
    open_cond = [*conditions, JobCard.status.in_(_OPEN)]
    overdue = db.scalar(
        select(func.count()).select_from(JobCard).where(*open_cond, JobCard.promised_at < now)
    )
    received_today = db.scalar(
        select(func.count())
        .select_from(JobCard)
        .where(*conditions, JobCard.received_at >= start_of_day)
    )
    mine = db.scalar(
        select(func.count())
        .select_from(JobCard)
        .where(
            *open_cond,
            exists(
                select(JobAssignment.id).where(
                    JobAssignment.job_card_id == JobCard.id,
                    JobAssignment.user_id == principal.user_id,
                    JobAssignment.unassigned_at.is_(None),
                )
            ),
        )
    )
    return JobSummaryCounts(
        by_status={s: by_status.get(s, 0) for s in JobStatus},
        open_total=sum(n for s, n in by_status.items() if s not in TERMINAL),
        overdue=overdue or 0,
        received_today=received_today or 0,
        my_assigned_open=mine or 0,
    )


# --------------------------------------------------------------------------- intake


def create_job_card(db: Session, principal: Principal, body: JobCardCreate) -> JobCardDetail:
    principal.require(P.JOB_CARDS_CREATE, body.branch_id)
    branch = get_scoped(db, Branch, body.branch_id, principal.organisation_id)
    if branch.archived_at is not None:
        raise ConflictError("This branch is archived.")
    customer = get_scoped(db, Customer, body.customer_id, principal.organisation_id)
    if customer.archived_at is not None:
        raise ConflictError("This customer is archived. Restore them first.")
    vehicle = db.scalar(
        select(Vehicle)
        .where(Vehicle.id == body.vehicle_id, Vehicle.organisation_id == principal.organisation_id)
        .with_for_update()
    )
    if vehicle is None:
        raise NotFoundError("Vehicle not found.")
    if vehicle.archived_at is not None:
        raise ConflictError("This vehicle is archived. Restore it first.")
    if vehicle.customer_id != customer.id:
        raise ConflictError(
            "This vehicle is registered to a different customer. Transfer it first if it has "
            "changed hands."
        )
    if body.service_bay_id:
        bay = get_scoped(db, ServiceBay, body.service_bay_id, principal.organisation_id)
        if bay.branch_id != branch.id or not bay.is_active:
            raise ConflictError("Choose an active service bay at this branch.")

    open_job = db.scalar(
        select(JobCard.job_number).where(
            JobCard.vehicle_id == vehicle.id, JobCard.status.in_(_OPEN)
        )
    )
    if open_job:
        raise ConflictError(
            f"This vehicle already has an open job card ({open_job}).",
            details={"open_job_number": open_job},
        )

    if body.intake_odometer_km is not None:
        last = vehicle.odometer_km
        if (
            last is not None
            and body.intake_odometer_km < last
            and not body.odometer_correction_reason
        ):
            raise OdometerDecreaseError(
                f"The odometer was last recorded at {last:,} km. Check the reading, or give a "
                "reason to record a lower value.",
                details={"current_odometer_km": last},
            )
        vehicle.odometer_km = body.intake_odometer_km
        vehicle.odometer_recorded_at = utcnow()

    job = JobCard(
        organisation_id=principal.organisation_id,
        branch_id=branch.id,
        job_number=numbering.allocate(
            db, principal.organisation_id, numbering.DocumentType.JOB_CARD
        ),
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_bay_id=body.service_bay_id,
        status=JobStatus.VEHICLE_RECEIVED.value,
        priority=body.priority,
        complaint=body.complaint,
        requested_work=body.requested_work,
        intake_odometer_km=body.intake_odometer_km,
        fuel_level=body.fuel_level,
        promised_at=body.promised_at,
        received_by_user_id=principal.user_id,
        version=1,
    )
    db.add(job)
    db.flush()
    db.add(
        JobStatusHistory(
            organisation_id=principal.organisation_id,
            job_card_id=job.id,
            from_status=None,
            to_status=JobStatus.VEHICLE_RECEIVED.value,
            changed_by_user_id=principal.user_id,
        )
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=branch.id,
        actor=principal,
        action="job_card.created",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Job {job.job_number} opened for {vehicle.registration_number or vehicle.vin} "
        f"({customer.display_name})",
        changes={
            "intake_odometer_km": body.intake_odometer_km,
            "odometer_correction_reason": body.odometer_correction_reason,
        }
        if body.odometer_correction_reason
        else None,
    )
    db.commit()
    return get_job_card(db, principal, job.id)


# --------------------------------------------------------------------------- updates


def update_job_card(
    db: Session, principal: Principal, job_id: uuid.UUID, body: JobCardUpdate
) -> JobCardDetail:
    job = get_visible_job_card(db, principal, job_id, lock=True)
    _require_open(job)
    _check_version(job, body.version)
    data = body.changes()
    data.pop("version")
    manage = principal.can(P.JOB_CARDS_MANAGE, job.branch_id)
    if not manage:
        work = principal.can(P.JOB_CARDS_WORK, job.branch_id) and _is_assigned(
            db, job.id, principal.user_id
        )
        if not work or set(data) - _WORK_FIELDS:
            raise PermissionDeniedError(
                "You can only update the diagnosis and work performed on jobs assigned to you."
            )
    if data.get("service_bay_id"):
        bay = get_scoped(db, ServiceBay, data["service_bay_id"], principal.organisation_id)
        if bay.branch_id != job.branch_id or not bay.is_active:
            raise ConflictError("Choose an active service bay at this branch.")

    changes: dict[str, list[Any]] = {}
    for key, value in data.items():
        old = getattr(job, key)
        if old != value:
            changes[key] = [old, value]
            setattr(job, key, value)
    if changes:
        job.version += 1
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            branch_id=job.branch_id,
            actor=principal,
            action="job_card.updated",
            entity_type="job_card",
            entity_id=job.id,
            summary=f"Job {job.job_number} updated ({', '.join(sorted(changes))})",
            changes=changes,
        )
    db.commit()
    return get_job_card(db, principal, job.id)


def transition(
    db: Session, principal: Principal, job_id: uuid.UUID, body: TransitionRequest
) -> JobCardDetail:
    job = get_visible_job_card(db, principal, job_id, lock=True)
    _check_version(job, body.version)
    current, target = JobStatus(job.status), body.to_status
    if not is_valid(current, target):
        raise InvalidStateTransitionError(
            f"A job that is '{LABELS[current]}' cannot move to '{LABELS[target]}'.",
            details={
                "from": current.value,
                "to": target.value,
                "allowed": sorted(s.value for s in TRANSITIONS[current]),
            },
        )
    assigned = _is_assigned(db, job.id, principal.user_id)
    if not _can_transition(principal, job, assigned, target):
        raise PermissionDeniedError(
            "You do not have permission to make this status change on this job."
        )
    if needs_approval(current, target) and not _has_customer_approval(db, job.id):
        raise ApprovalRequiredError(
            "Chargeable work cannot start until the customer has approved the quotation, or an "
            "authorised user records an approval exception.",
            details={"to": target.value},
        )

    job.status = target.value
    job.version += 1
    if target == JobStatus.COMPLETED:
        job.collected_at = utcnow()
        job.collected_by_name = body.collected_by_name
        job.handover_notes = body.handover_notes
    if target == JobStatus.CANCELLED:
        job.cancellation_reason = body.cancellation_reason
    note = (
        body.note
        or body.cancellation_reason
        or (f"Collected by {body.collected_by_name}" if target == JobStatus.COMPLETED else None)
    )
    db.add(
        JobStatusHistory(
            organisation_id=principal.organisation_id,
            job_card_id=job.id,
            from_status=current.value,
            to_status=target.value,
            note=note,
            changed_by_user_id=principal.user_id,
        )
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="job_card.status_changed",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Job {job.job_number}: {LABELS[current]} → {LABELS[target]}",
        changes={"status": [current.value, target.value], "note": note},
    )
    db.commit()
    return get_job_card(db, principal, job.id)


# --------------------------------------------------------------------------- assignments


def workers_for_branch(db: Session, organisation_id: uuid.UUID, branch_id: uuid.UUID) -> list[User]:
    users = db.scalars(
        select(User)
        .where(
            User.organisation_id == organisation_id,
            User.is_active,
            User.password_hash.is_not(None),
        )
        .order_by(User.full_name)
    )
    return [u for u in users if load_principal(db, u, None).can(P.JOB_CARDS_WORK, branch_id)]


def assignable_users(db: Session, principal: Principal, job_id: uuid.UUID) -> list[AssignableUser]:
    job = get_visible_job_card(db, principal, job_id)
    principal.require(P.JOB_CARDS_ASSIGN, job.branch_id)
    workers = workers_for_branch(db, principal.organisation_id, job.branch_id)
    loads = (
        dict(
            db.execute(
                select(JobAssignment.user_id, func.count())
                .join(JobCard, JobCard.id == JobAssignment.job_card_id)
                .where(
                    JobAssignment.user_id.in_([u.id for u in workers]),
                    JobAssignment.unassigned_at.is_(None),
                    JobCard.status.in_(_OPEN),
                )
                .group_by(JobAssignment.user_id)
            ).all()
        )
        if workers
        else {}
    )
    return [
        AssignableUser(id=u.id, full_name=u.full_name, active_jobs=loads.get(u.id, 0))
        for u in workers
    ]


def assign(
    db: Session, principal: Principal, job_id: uuid.UUID, user_id: uuid.UUID
) -> JobCardDetail:
    job = get_visible_job_card(db, principal, job_id, lock=True)
    principal.require(P.JOB_CARDS_ASSIGN, job.branch_id)
    _require_open(job)
    user = db.scalar(
        select(User).where(User.id == user_id, User.organisation_id == principal.organisation_id)
    )
    if user is None:
        raise NotFoundError("User not found.")
    if not user.is_active or user.password_hash is None:
        raise ConflictError("Only active users can be assigned.")
    if not load_principal(db, user, None).can(P.JOB_CARDS_WORK, job.branch_id):
        raise ConflictError(
            f"{user.full_name} cannot work on jobs at this branch. Give them a role with "
            "'Work on assigned jobs' for this branch first."
        )
    db.add(
        JobAssignment(
            organisation_id=principal.organisation_id,
            job_card_id=job.id,
            user_id=user.id,
            assigned_by_user_id=principal.user_id,
        )
    )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"{user.full_name} is already assigned to this job.") from exc
    job.version += 1
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="job_card.assigned",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"{user.full_name} assigned to job {job.job_number}",
        changes={"user_id": user.id},
    )
    db.commit()
    return get_job_card(db, principal, job.id)


def unassign(
    db: Session, principal: Principal, job_id: uuid.UUID, user_id: uuid.UUID
) -> JobCardDetail:
    job = get_visible_job_card(db, principal, job_id, lock=True)
    principal.require(P.JOB_CARDS_ASSIGN, job.branch_id)
    assignment = db.scalar(
        select(JobAssignment).where(
            JobAssignment.job_card_id == job.id,
            JobAssignment.user_id == user_id,
            JobAssignment.unassigned_at.is_(None),
        )
    )
    if assignment is None:
        raise NotFoundError("This user is not assigned to the job.")
    assignment.unassigned_at = utcnow()
    assignment.unassigned_by_user_id = principal.user_id
    job.version += 1
    name = _names(db, [user_id]).get(user_id, "User")
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="job_card.unassigned",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"{name} unassigned from job {job.job_number}",
        changes={"user_id": user_id},
    )
    db.commit()
    return get_job_card(db, principal, job.id)


# --------------------------------------------------------------------------- notes and exceptions


def add_note(db: Session, principal: Principal, job_id: uuid.UUID, body: NoteCreate) -> NoteRead:
    job = get_visible_job_card(db, principal, job_id)
    allowed = (
        principal.can(P.JOB_CARDS_MANAGE, job.branch_id)
        or principal.can(P.JOB_CARDS_CREATE, job.branch_id)
        or (
            principal.can(P.JOB_CARDS_WORK, job.branch_id)
            and _is_assigned(db, job.id, principal.user_id)
        )
    )
    if not allowed:
        raise PermissionDeniedError("You cannot add notes to this job.")
    note = JobNote(
        organisation_id=principal.organisation_id,
        job_card_id=job.id,
        author_user_id=principal.user_id,
        body=body.body,
        visibility=body.visibility,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return NoteRead(
        id=note.id,
        body=note.body,
        visibility=note.visibility,  # type: ignore[arg-type]
        author=principal.full_name,
        created_at=note.created_at,
    )


def authorise_exception(
    db: Session, principal: Principal, job_id: uuid.UUID, body: ExceptionCreate
) -> JobCardDetail:
    job = get_visible_job_card(db, principal, job_id, lock=True)
    principal.require(P.JOB_CARDS_AUTHORISE_EXCEPTION, job.branch_id)
    _require_open(job)
    currency = db.scalar(
        select(OrganisationSettings.currency_code).where(
            OrganisationSettings.organisation_id == principal.organisation_id
        )
    )
    exception = JobApprovalException(
        organisation_id=principal.organisation_id,
        job_card_id=job.id,
        authorised_by_user_id=principal.user_id,
        currency_code=currency or "NAD",
        **body.model_dump(),
    )
    db.add(exception)
    db.flush()
    job.version += 1
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="job_card.approval_exception_authorised",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Approval exception ({body.exception_type}) authorised on job {job.job_number}",
        changes=body.model_dump(),
    )
    db.commit()
    return get_job_card(db, principal, job.id)


def revoke_exception(
    db: Session, principal: Principal, job_id: uuid.UUID, exception_id: uuid.UUID, reason: str
) -> JobCardDetail:
    job = get_visible_job_card(db, principal, job_id, lock=True)
    principal.require(P.JOB_CARDS_AUTHORISE_EXCEPTION, job.branch_id)
    exception = db.scalar(
        select(JobApprovalException).where(
            JobApprovalException.id == exception_id, JobApprovalException.job_card_id == job.id
        )
    )
    if exception is None:
        raise NotFoundError("Approval exception not found.")
    if exception.revoked_at is not None:
        raise ConflictError("This exception has already been revoked.")
    exception.revoked_at = utcnow()
    exception.revoked_by_user_id = principal.user_id
    exception.revoke_reason = reason
    job.version += 1
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="job_card.approval_exception_revoked",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Approval exception revoked on job {job.job_number}",
        changes={"exception_id": exception.id, "reason": reason},
    )
    db.commit()
    return get_job_card(db, principal, job.id)
