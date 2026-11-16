"""Parts for jobs: reservations, issues and returns (CLAUDE.md §3.7).

- Stock can be reserved and issued only for jobs that are authorised: the customer
  approved the quotation, or an authorised user recorded an approval exception.
- Parts are consumed (issued) when they are actually fitted, not when quoted. Issuing
  draws first on the job's own reservations at that location, then on free stock.
- Returns are limited to what was issued to the job, net of earlier returns.
- Locations must belong to the job's branch.
- Completing or cancelling a job releases whatever is still reserved for it.
- Every request that changes stock or reservations carries an Idempotency-Key.
"""

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import (
    JobCard,
    OrganisationSettings,
    Part,
    StockLevel,
    StockLocation,
    StockMovement,
    StockReservation,
    User,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.inventory import (
    JobPartsCapabilities,
    JobPartsRead,
    JobPartsRequest,
    JobPartsReturn,
    ReleaseRequest,
    ReservationRead,
    UsedPartRead,
)
from app.schemas.job_card import Ref
from app.services import audit
from app.services.idempotency import check_replay, fingerprint
from app.services.inventory import (
    can_see_costs,
    check_whole,
    existing_operation,
    get_location,
    load_parts,
    lock_levels,
    movement_read,
    movement_rows,
    record_movement,
    start_operation,
)
from app.services.job_cards import (
    ApprovalRequiredError,
    _has_customer_approval,
    get_visible_job_card,
)
from app.services.job_workflow import TERMINAL, JobStatus

ZERO = Decimal("0.00")


def _job(
    db: Session, principal: Principal, job_id: uuid.UUID, permission: str, *, lock: bool = False
) -> JobCard:
    job = get_visible_job_card(db, principal, job_id, lock=lock)
    principal.require(permission, job.branch_id)
    return job


def _authorised(db: Session, job: JobCard) -> bool:
    return JobStatus(job.status) not in TERMINAL and _has_customer_approval(db, job.id)


def _require_authorised(db: Session, job: JobCard) -> None:
    if JobStatus(job.status) in TERMINAL:
        raise ConflictError("This job is closed.")
    if not _has_customer_approval(db, job.id):
        raise ApprovalRequiredError(
            "Parts can be reserved or issued only after the customer has approved the "
            "quotation, or an authorised user records an approval exception."
        )


def _job_location(
    db: Session, principal: Principal, job: JobCard, location_id: uuid.UUID
) -> StockLocation:
    loc = get_location(db, principal, location_id)
    if loc.branch_id != job.branch_id:
        raise ConflictError("Use a stock location in the job's branch.")
    return loc


def _replay(
    db: Session, principal: Principal, job_id: uuid.UUID, key: str, print_: str
) -> JobPartsRead | None:
    existing = existing_operation(db, principal.organisation_id, key)
    if existing is None:
        return None
    check_replay(existing.request_fingerprint, print_)
    return read(db, principal, job_id)


def net_issued(db: Session, job_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    """Quantity fitted to the job per part: issues minus returns (positive)."""
    return {
        part_id: -total
        for part_id, total in db.execute(
            select(StockMovement.part_id, func.sum(StockMovement.quantity))
            .where(
                StockMovement.job_card_id == job_id,
                StockMovement.kind.in_(("issue", "return")),
            )
            .group_by(StockMovement.part_id)
        )
        if total
    }


# --------------------------------------------------------------------------- read


def read(db: Session, principal: Principal, job_id: uuid.UUID) -> JobPartsRead:
    job = _job(db, principal, job_id, P.INVENTORY_VIEW)
    reservations = db.execute(
        select(StockReservation, Part, StockLocation.name, User.full_name)
        .join(Part, Part.id == StockReservation.part_id)
        .join(StockLocation, StockLocation.id == StockReservation.location_id)
        .join(User, User.id == StockReservation.created_by_user_id)
        .where(StockReservation.job_card_id == job.id)
        .order_by(StockReservation.status.desc(), StockReservation.created_at)
    ).all()
    issued = net_issued(db, job.id)
    parts = (
        {p.id: p for p in db.scalars(select(Part).where(Part.id.in_(list(issued))))}
        if issued
        else {}
    )
    movements = db.execute(
        movement_rows(
            db,
            [
                StockMovement.job_card_id == job.id,
                StockMovement.kind.in_(("issue", "return")),
            ],
        ).order_by(StockMovement.created_at.desc(), StockMovement.id)
    ).all()
    locations = db.execute(
        select(StockLocation.id, StockLocation.name)
        .where(StockLocation.branch_id == job.branch_id, StockLocation.archived_at.is_(None))
        .order_by(StockLocation.is_default.desc(), StockLocation.name)
    ).all()
    can_issue = principal.can(P.INVENTORY_ISSUE, job.branch_id)
    authorised = _authorised(db, job)
    costs = can_see_costs(principal)
    return JobPartsRead(
        job_card_id=job.id,
        authorised=authorised,
        currency_code=db.scalar(
            select(OrganisationSettings.currency_code).where(
                OrganisationSettings.organisation_id == job.organisation_id
            )
        )
        or "NAD",
        capabilities=JobPartsCapabilities(
            reserve=can_issue and authorised,
            issue=can_issue and authorised,
            return_parts=can_issue and bool(issued),
            release=can_issue,
        ),
        locations=[Ref(id=i, name=n) for i, n in locations],
        reservations=[
            ReservationRead(
                id=r.id,
                part=Ref(id=part.id, name=part.name),
                sku=part.sku,
                unit=part.unit,  # type: ignore[arg-type]
                location=Ref(id=r.location_id, name=loc_name),
                quantity=r.quantity,
                issued_quantity=r.issued_quantity,
                released_quantity=r.released_quantity,
                outstanding=r.quantity - r.issued_quantity - r.released_quantity,
                status=r.status,  # type: ignore[arg-type]
                release_reason=r.release_reason,
                created_by=user,
                created_at=r.created_at,
            )
            for r, part, loc_name, user in reservations
        ],
        used=sorted(
            (
                UsedPartRead(
                    part=Ref(id=pid, name=parts[pid].name),
                    sku=parts[pid].sku,
                    unit=parts[pid].unit,  # type: ignore[arg-type]
                    issued=q,
                    selling_price=parts[pid].selling_price,
                    value=(q * parts[pid].selling_price).quantize(Decimal("0.01")),
                )
                for pid, q in issued.items()
            ),
            key=lambda u: u.sku,
        ),
        movements=[movement_read(r, costs) for r in movements],
    )


# --------------------------------------------------------------------------- reserve


def reserve(
    db: Session, principal: Principal, job_id: uuid.UUID, body: JobPartsRequest, key: str
) -> tuple[JobPartsRead, bool]:
    print_ = fingerprint({"op": "reserve", "job": str(job_id), **body.model_dump(mode="json")})
    if (done := _replay(db, principal, job_id, key, print_)) is not None:
        return done, False
    job = _job(db, principal, job_id, P.INVENTORY_ISSUE, lock=True)
    _require_authorised(db, job)
    loc = _job_location(db, principal, job, body.location_id)
    parts = load_parts(db, principal, [line.part_id for line in body.lines])
    for line in body.lines:
        check_whole(parts[line.part_id], line.quantity)
    op = start_operation(
        db, principal, kind="reservation", key=key, print_=print_, job_card_id=job.id
    )
    if op is None:
        return _replay(db, principal, job_id, key, print_), False  # type: ignore[return-value]
    levels = lock_levels(db, [(loc, pid) for pid in parts])
    for line in body.lines:
        part = parts[line.part_id]
        level = levels[(loc.id, part.id)]
        available = level.on_hand - level.reserved
        if line.quantity > available:
            raise ConflictError(
                f"{part.sku}: only {available} available at {loc.name}.",
                details={"part_id": str(part.id), "available": str(available)},
            )
        level.reserved += line.quantity
        db.add(
            StockReservation(
                organisation_id=job.organisation_id,
                branch_id=job.branch_id,
                job_card_id=job.id,
                location_id=loc.id,
                part_id=part.id,
                operation_id=op.id,
                quantity=line.quantity,
                created_by_user_id=principal.user_id,
            )
        )
    audit.record(
        db,
        organisation_id=job.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="stock.reserved",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Reserved for {job.job_number} at {loc.name}: "
        + ", ".join(f"{parts[ln.part_id].sku} {ln.quantity}" for ln in body.lines),
    )
    db.commit()
    return read(db, principal, job.id), True


def _close_if_done(r: StockReservation) -> None:
    if r.issued_quantity + r.released_quantity >= r.quantity:
        r.status = "closed"
        r.closed_at = utcnow()


def _release(
    db: Session, reservations: list[StockReservation], reason: str
) -> list[tuple[StockReservation, Decimal]]:
    """Release what is outstanding on each open reservation. Locks the stock levels first
    (fixed order), then adjusts reserved."""
    if not reservations:
        return []
    locs = {
        loc.id: loc
        for loc in db.scalars(
            select(StockLocation).where(StockLocation.id.in_({r.location_id for r in reservations}))
        )
    }
    levels = lock_levels(db, [(locs[r.location_id], r.part_id) for r in reservations])
    released = []
    for r in reservations:
        outstanding = r.quantity - r.issued_quantity - r.released_quantity
        if outstanding <= 0:
            continue
        levels[(r.location_id, r.part_id)].reserved -= outstanding
        r.released_quantity += outstanding
        r.release_reason = reason
        _close_if_done(r)
        released.append((r, outstanding))
    return released


def release(
    db: Session,
    principal: Principal,
    job_id: uuid.UUID,
    reservation_id: uuid.UUID,
    body: ReleaseRequest,
) -> JobPartsRead:
    job = _job(db, principal, job_id, P.INVENTORY_ISSUE, lock=True)
    r = db.scalar(
        select(StockReservation)
        .where(StockReservation.id == reservation_id, StockReservation.job_card_id == job.id)
        .with_for_update()
    )
    if r is None:
        raise NotFoundError("Reservation not found.")
    if r.status != "open":
        raise ConflictError("This reservation is already closed.")
    done = _release(db, [r], body.reason)
    sku = db.scalar(select(Part.sku).where(Part.id == r.part_id))
    audit.record(
        db,
        organisation_id=job.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="stock.reservation_released",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Released {done[0][1] if done else 0} {sku} reserved for {job.job_number}: "
        f"{body.reason}",
    )
    db.commit()
    return read(db, principal, job.id)


def release_all_for_job(db: Session, principal: Principal, job: JobCard, reason: str) -> None:
    """Called inside the job status transition when a job is completed or cancelled."""
    open_ = list(
        db.scalars(
            select(StockReservation)
            .where(StockReservation.job_card_id == job.id, StockReservation.status == "open")
            .with_for_update()
        )
    )
    done = _release(db, open_, reason)
    if done:
        audit.record(
            db,
            organisation_id=job.organisation_id,
            branch_id=job.branch_id,
            actor=principal,
            action="stock.reservation_released",
            entity_type="job_card",
            entity_id=job.id,
            summary=f"Reservations for {job.job_number} released: {reason}",
        )


# --------------------------------------------------------------------------- issue / return


def issue(
    db: Session, principal: Principal, job_id: uuid.UUID, body: JobPartsRequest, key: str
) -> tuple[JobPartsRead, bool]:
    print_ = fingerprint({"op": "issue", "job": str(job_id), **body.model_dump(mode="json")})
    if (done := _replay(db, principal, job_id, key, print_)) is not None:
        return done, False
    job = _job(db, principal, job_id, P.INVENTORY_ISSUE, lock=True)
    _require_authorised(db, job)
    loc = _job_location(db, principal, job, body.location_id)
    parts = load_parts(db, principal, [line.part_id for line in body.lines])
    for line in body.lines:
        check_whole(parts[line.part_id], line.quantity)
    op = start_operation(db, principal, kind="issue", key=key, print_=print_, job_card_id=job.id)
    if op is None:
        return _replay(db, principal, job_id, key, print_), False  # type: ignore[return-value]
    levels = lock_levels(db, [(loc, pid) for pid in parts])
    open_by_part: dict[uuid.UUID, list[StockReservation]] = defaultdict(list)
    for r in db.scalars(
        select(StockReservation)
        .where(
            StockReservation.job_card_id == job.id,
            StockReservation.location_id == loc.id,
            StockReservation.part_id.in_(list(parts)),
            StockReservation.status == "open",
        )
        .order_by(StockReservation.created_at)
        .with_for_update()
    ):
        open_by_part[r.part_id].append(r)

    for line in body.lines:
        part = parts[line.part_id]
        level: StockLevel = levels[(loc.id, part.id)]
        mine = sum(
            (r.quantity - r.issued_quantity - r.released_quantity for r in open_by_part[part.id]),
            ZERO,
        )
        from_reserved = min(line.quantity, mine)
        from_free = line.quantity - from_reserved
        free = level.on_hand - level.reserved
        if from_free > free:
            raise ConflictError(
                f"{part.sku}: {mine} reserved for this job and {free} free at {loc.name}.",
                details={"part_id": str(part.id), "reserved_for_job": str(mine), "free": str(free)},
            )
        remaining = from_reserved
        for r in open_by_part[part.id]:
            if remaining <= 0:
                break
            take = min(remaining, r.quantity - r.issued_quantity - r.released_quantity)
            r.issued_quantity += take
            _close_if_done(r)
            remaining -= take
        if from_reserved:
            # Lower reserved before the stock leaves, so reserved <= on_hand holds.
            level.reserved -= from_reserved
            db.flush()
        record_movement(db, principal, op, loc, part, "issue", -line.quantity, job_card_id=job.id)
    audit.record(
        db,
        organisation_id=job.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="stock.issued",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Issued to {job.job_number} from {loc.name}: "
        + ", ".join(f"{parts[ln.part_id].sku} {ln.quantity}" for ln in body.lines),
    )
    db.commit()
    return read(db, principal, job.id), True


def return_parts(
    db: Session, principal: Principal, job_id: uuid.UUID, body: JobPartsReturn, key: str
) -> tuple[JobPartsRead, bool]:
    print_ = fingerprint({"op": "return", "job": str(job_id), **body.model_dump(mode="json")})
    if (done := _replay(db, principal, job_id, key, print_)) is not None:
        return done, False
    job = _job(db, principal, job_id, P.INVENTORY_ISSUE, lock=True)
    loc = _job_location(db, principal, job, body.location_id)
    parts = load_parts(db, principal, [line.part_id for line in body.lines])
    issued = net_issued(db, job.id)
    for line in body.lines:
        part = parts[line.part_id]
        check_whole(part, line.quantity)
        if line.quantity > issued.get(part.id, ZERO):
            raise ConflictError(
                f"{part.sku}: only {issued.get(part.id, ZERO)} was issued to this job.",
                details={"part_id": str(part.id), "issued": str(issued.get(part.id, ZERO))},
            )
    op = start_operation(
        db, principal, kind="return", key=key, print_=print_, reason=body.reason, job_card_id=job.id
    )
    if op is None:
        return _replay(db, principal, job_id, key, print_), False  # type: ignore[return-value]
    lock_levels(db, [(loc, pid) for pid in parts])
    for line in body.lines:
        record_movement(
            db, principal, op, loc, parts[line.part_id], "return", line.quantity, job_card_id=job.id
        )
    audit.record(
        db,
        organisation_id=job.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="stock.returned",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Returned from {job.job_number} to {loc.name}: "
        + ", ".join(f"{parts[ln.part_id].sku} {ln.quantity}" for ln in body.lines)
        + f" ({body.reason})",
    )
    db.commit()
    return read(db, principal, job.id), True
