"""Parts catalogue, stock locations, stock levels and stock-changing operations
(CLAUDE.md §3.7).

Integrity rules:
- The movement ledger is the source of truth. Stock on hand is changed only by inserting
  movements; a database trigger applies each movement to `stock_levels`.
- Every operation locks the affected stock-level rows in a fixed order (location, part),
  checks the result, then writes its movements in one transaction.
- Stock never goes below zero, and never below what is reserved for jobs.
- Each operation carries an Idempotency-Key, so a retried request is applied once.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.time import utcnow
from app.models import (
    Branch,
    JobCard,
    Part,
    PartCategory,
    StockLevel,
    StockLocation,
    StockMovement,
    StockOperation,
    TaxRate,
    User,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.inventory import (
    WHOLE_UNITS,
    AdjustmentCreate,
    CategoryInput,
    CategoryRead,
    LevelRead,
    LocationCreate,
    LocationRead,
    LocationUpdate,
    MinLevelUpdate,
    MovementRead,
    OperationRead,
    PartCapabilities,
    PartCreate,
    PartListItem,
    PartRead,
    PartUpdate,
    StockSummary,
    TransferCreate,
)
from app.schemas.job_card import Ref
from app.services import audit
from app.services.common import get_scoped
from app.services.idempotency import check_replay, fingerprint

ZERO = Decimal("0.00")


# --------------------------------------------------------------------------- access


def visible_branches(principal: Principal) -> set[uuid.UUID] | None:
    branches = principal.branch_ids_with(P.INVENTORY_VIEW)
    if branches is not None and not branches:
        raise PermissionDeniedError("You do not have permission to view inventory.")
    return branches


def can_see_costs(principal: Principal) -> bool:
    return principal.can(P.INVENTORY_CATALOGUE) or principal.can_in_any_branch(P.INVENTORY_ADJUST)


def _in(column: Any, branches: set[uuid.UUID] | None) -> list[Any]:
    return [] if branches is None else [column.in_(branches)]


def _location(
    db: Session, principal: Principal, location_id: uuid.UUID, *, active: bool = True
) -> StockLocation:
    loc = db.scalar(
        select(StockLocation).where(
            StockLocation.id == location_id,
            StockLocation.organisation_id == principal.organisation_id,
        )
    )
    if loc is None or not principal.can(P.INVENTORY_VIEW, loc.branch_id):
        raise NotFoundError("Stock location not found.")
    if active and loc.archived_at is not None:
        raise ConflictError(f"{loc.name} is archived.")
    return loc


def _check_whole(part: Part, quantity: Decimal) -> None:
    if part.unit in WHOLE_UNITS and quantity != quantity.to_integral_value():
        raise ConflictError(
            f"{part.sku} is counted in whole units ({part.unit}).",
            details={"part_id": str(part.id)},
        )


def _parts(db: Session, principal: Principal, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Part]:
    wanted = list(ids)
    if len(set(wanted)) != len(wanted):
        raise ConflictError("Each part may appear only once.")
    found = {
        p.id: p
        for p in db.scalars(
            select(Part).where(
                Part.id.in_(wanted), Part.organisation_id == principal.organisation_id
            )
        )
    }
    for pid in wanted:
        if pid not in found:
            raise NotFoundError("Part not found.", details={"part_id": str(pid)})
        if found[pid].archived_at is not None:
            raise ConflictError(
                f"{found[pid].sku} is archived. Restore it first.", details={"part_id": str(pid)}
            )
    return found


# --------------------------------------------------------------------------- categories


def list_categories(db: Session, principal: Principal) -> list[CategoryRead]:
    principal.require_in_any_branch(P.INVENTORY_VIEW)
    counts = dict(
        db.execute(
            select(Part.category_id, func.count())
            .where(Part.organisation_id == principal.organisation_id, Part.archived_at.is_(None))
            .group_by(Part.category_id)
        ).all()
    )
    return [
        CategoryRead(
            id=c.id, name=c.name, archived_at=c.archived_at, part_count=counts.get(c.id, 0)
        )
        for c in db.scalars(
            select(PartCategory)
            .where(PartCategory.organisation_id == principal.organisation_id)
            .order_by(PartCategory.name)
        )
    ]


def save_category(
    db: Session, principal: Principal, body: CategoryInput, category_id: uuid.UUID | None = None
) -> CategoryRead:
    principal.require(P.INVENTORY_CATALOGUE)
    if category_id:
        cat = get_scoped(db, PartCategory, category_id, principal.organisation_id)
        cat.name = body.name
    else:
        cat = PartCategory(organisation_id=principal.organisation_id, name=body.name)
        db.add(cat)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"A category named {body.name} already exists.") from exc
    db.commit()
    return next(c for c in list_categories(db, principal) if c.id == cat.id)


# --------------------------------------------------------------------------- parts


def _summaries(
    db: Session, part_ids: list[uuid.UUID], branches: set[uuid.UUID] | None
) -> dict[uuid.UUID, StockSummary]:
    if not part_ids:
        return {}
    available = StockLevel.on_hand - StockLevel.reserved
    low = func.count().filter(
        and_(StockLevel.min_quantity.is_not(None), available <= StockLevel.min_quantity)
    )
    rows = db.execute(
        select(
            StockLevel.part_id,
            func.sum(StockLevel.on_hand),
            func.sum(StockLevel.reserved),
            low,
        )
        .where(StockLevel.part_id.in_(part_ids), *_in(StockLevel.branch_id, branches))
        .group_by(StockLevel.part_id)
    ).all()
    out = {
        pid: StockSummary(on_hand=oh, reserved=res, available=oh - res, low_locations=lo)
        for pid, oh, res, lo in rows
    }
    empty = StockSummary(on_hand=ZERO, reserved=ZERO, available=ZERO, low_locations=0)
    return {pid: out.get(pid, empty) for pid in part_ids}


def _ref(model: Any, id_: uuid.UUID | None, db: Session) -> Ref | None:
    if id_ is None:
        return None
    return Ref(id=id_, name=db.scalar(select(model.name).where(model.id == id_)) or "")


def _list_item(
    db: Session, p: Part, stock: StockSummary, costs: bool, categories: dict[uuid.UUID, str]
) -> PartListItem:
    return PartListItem(
        id=p.id,
        sku=p.sku,
        name=p.name,
        category=Ref(id=p.category_id, name=categories.get(p.category_id, ""))
        if p.category_id
        else None,
        unit=p.unit,  # type: ignore[arg-type]
        manufacturer_part_number=p.manufacturer_part_number,
        selling_price=p.selling_price,
        cost_price=p.cost_price if costs else None,
        archived_at=p.archived_at,
        stock=stock,
    )


def list_parts(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    search: str | None = None,
    category_id: uuid.UUID | None = None,
    low_stock: bool = False,
    include_archived: bool = False,
) -> tuple[list[PartListItem], int]:
    branches = visible_branches(principal)
    conditions: list[Any] = [Part.organisation_id == principal.organisation_id]
    if not include_archived:
        conditions.append(Part.archived_at.is_(None))
    if category_id:
        conditions.append(Part.category_id == category_id)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                Part.sku.ilike(term),
                Part.name.ilike(term),
                Part.manufacturer_part_number.ilike(term),
            )
        )
    if low_stock:
        conditions.append(
            Part.id.in_(
                select(StockLevel.part_id).where(
                    StockLevel.min_quantity.is_not(None),
                    StockLevel.on_hand - StockLevel.reserved <= StockLevel.min_quantity,
                    *_in(StockLevel.branch_id, branches),
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(Part).where(*conditions)) or 0
    parts = list(
        db.scalars(
            select(Part)
            .where(*conditions)
            .order_by(Part.sku)
            .limit(params.page_size)
            .offset(params.offset)
        )
    )
    stock = _summaries(db, [p.id for p in parts], branches)
    categories = _category_names(db, principal.organisation_id)
    costs = can_see_costs(principal)
    return [_list_item(db, p, stock[p.id], costs, categories) for p in parts], total


def _category_names(db: Session, organisation_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(
        db.execute(
            select(PartCategory.id, PartCategory.name).where(
                PartCategory.organisation_id == organisation_id
            )
        ).all()
    )


def _load_part(db: Session, principal: Principal, part_id: uuid.UUID) -> Part:
    visible_branches(principal)
    return get_scoped(db, Part, part_id, principal.organisation_id)


def read_part(db: Session, principal: Principal, part: Part) -> PartRead:
    branches = visible_branches(principal)
    stock = _summaries(db, [part.id], branches)[part.id]
    base = _list_item(
        db, part, stock, can_see_costs(principal), _category_names(db, part.organisation_id)
    )
    rows = db.execute(
        select(StockLocation, Branch.name, StockLevel)
        .join(Branch, Branch.id == StockLocation.branch_id)
        .outerjoin(
            StockLevel,
            and_(StockLevel.location_id == StockLocation.id, StockLevel.part_id == part.id),
        )
        .where(
            StockLocation.organisation_id == part.organisation_id,
            or_(StockLocation.archived_at.is_(None), StockLevel.on_hand > 0),
            *_in(StockLocation.branch_id, branches),
        )
        .order_by(Branch.name, StockLocation.is_default.desc(), StockLocation.name)
    ).all()
    levels = []
    for loc, branch_name, level in rows:
        on_hand = level.on_hand if level else ZERO
        reserved = level.reserved if level else ZERO
        minimum = level.min_quantity if level else None
        levels.append(
            LevelRead(
                location=Ref(id=loc.id, name=loc.name),
                branch=Ref(id=loc.branch_id, name=branch_name),
                on_hand=on_hand,
                reserved=reserved,
                available=on_hand - reserved,
                min_quantity=minimum,
                is_low=minimum is not None and on_hand - reserved <= minimum,
                can_adjust=principal.can(P.INVENTORY_ADJUST, loc.branch_id)
                and loc.archived_at is None,
                can_transfer=principal.can(P.INVENTORY_TRANSFER, loc.branch_id)
                and loc.archived_at is None,
            )
        )
    manage = principal.can(P.INVENTORY_CATALOGUE)
    return PartRead(
        **base.model_dump(),
        description=part.description,
        manufacturer=part.manufacturer,
        tax_rate=_ref(TaxRate, part.tax_rate_id, db),
        created_at=part.created_at,
        updated_at=part.updated_at,
        levels=levels,
        capabilities=PartCapabilities(edit=manage, archive=manage),
    )


def get_part(db: Session, principal: Principal, part_id: uuid.UUID) -> PartRead:
    return read_part(db, principal, _load_part(db, principal, part_id))


def _validate_refs(
    db: Session,
    organisation_id: uuid.UUID,
    category_id: uuid.UUID | None,
    tax_rate_id: uuid.UUID | None,
) -> None:
    if category_id:
        get_scoped(db, PartCategory, category_id, organisation_id)
    if tax_rate_id:
        rate = get_scoped(db, TaxRate, tax_rate_id, organisation_id)
        if not rate.is_active:
            raise ConflictError("Choose an active tax rate.")


def _flush_part(db: Session, sku: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"SKU {sku} is already in use.", details={"field": "sku"}) from exc


def create_part(db: Session, principal: Principal, body: PartCreate) -> PartRead:
    principal.require(P.INVENTORY_CATALOGUE)
    _validate_refs(db, principal.organisation_id, body.category_id, body.tax_rate_id)
    part = Part(organisation_id=principal.organisation_id, **body.model_dump())
    db.add(part)
    _flush_part(db, body.sku)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="part.created",
        entity_type="part",
        entity_id=part.id,
        summary=f"Part {part.sku} {part.name} added to the catalogue",
    )
    db.commit()
    return read_part(db, principal, part)


def update_part(
    db: Session, principal: Principal, part_id: uuid.UUID, body: PartUpdate
) -> PartRead:
    principal.require(P.INVENTORY_CATALOGUE)
    part = get_scoped(db, Part, part_id, principal.organisation_id)
    changes = body.changes()
    _validate_refs(
        db, principal.organisation_id, changes.get("category_id"), changes.get("tax_rate_id")
    )
    before = {k: getattr(part, k) for k in changes}
    for k, v in changes.items():
        setattr(part, k, v)
    _flush_part(db, part.sku)
    diff = audit.diff(before, changes)
    if diff:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="part.updated",
            entity_type="part",
            entity_id=part.id,
            summary=f"Part {part.sku} updated: {', '.join(sorted(diff))}",
            changes=diff,
        )
    db.commit()
    return read_part(db, principal, part)


def set_archived(db: Session, principal: Principal, part_id: uuid.UUID, archived: bool) -> PartRead:
    principal.require(P.INVENTORY_CATALOGUE)
    part = get_scoped(db, Part, part_id, principal.organisation_id)
    if archived:
        held = db.scalar(
            select(func.coalesce(func.sum(StockLevel.on_hand), 0)).where(
                StockLevel.part_id == part.id
            )
        )
        if held:
            raise ConflictError(
                f"{part.sku} still has {held} in stock. Adjust or transfer it out first."
            )
    part.archived_at = utcnow() if archived else None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="part.archived" if archived else "part.restored",
        entity_type="part",
        entity_id=part.id,
        summary=f"Part {part.sku} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return read_part(db, principal, part)


# --------------------------------------------------------------------------- locations


def list_locations(
    db: Session, principal: Principal, branch_id: uuid.UUID | None = None
) -> list[LocationRead]:
    branches = visible_branches(principal)
    conditions: list[Any] = [
        StockLocation.organisation_id == principal.organisation_id,
        *_in(StockLocation.branch_id, branches),
    ]
    if branch_id:
        conditions.append(StockLocation.branch_id == branch_id)
    totals = {
        loc_id: (n, units)
        for loc_id, n, units in db.execute(
            select(
                StockLevel.location_id,
                func.count().filter(StockLevel.on_hand > 0),
                func.sum(StockLevel.on_hand),
            ).group_by(StockLevel.location_id)
        )
    }
    rows = db.execute(
        select(StockLocation, Branch.name)
        .join(Branch, Branch.id == StockLocation.branch_id)
        .where(*conditions)
        .order_by(
            Branch.name,
            StockLocation.archived_at.is_not(None),
            StockLocation.is_default.desc(),
            StockLocation.name,
        )
    ).all()
    return [
        LocationRead(
            id=loc.id,
            name=loc.name,
            branch=Ref(id=loc.branch_id, name=bname),
            is_default=loc.is_default,
            archived_at=loc.archived_at,
            part_count=totals.get(loc.id, (0, ZERO))[0],
            units_on_hand=totals.get(loc.id, (0, ZERO))[1] or ZERO,
        )
        for loc, bname in rows
    ]


def _location_read(db: Session, principal: Principal, loc_id: uuid.UUID) -> LocationRead:
    return next(x for x in list_locations(db, principal) if x.id == loc_id)


def create_location(db: Session, principal: Principal, body: LocationCreate) -> LocationRead:
    branch = get_scoped(db, Branch, body.branch_id, principal.organisation_id)
    principal.require(P.INVENTORY_ADJUST, branch.id)
    loc = StockLocation(
        organisation_id=principal.organisation_id, branch_id=branch.id, name=body.name
    )
    db.add(loc)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"{branch.name} already has a location named {body.name}.") from exc
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=branch.id,
        actor=principal,
        action="stock_location.created",
        entity_type="stock_location",
        entity_id=loc.id,
        summary=f"Stock location {loc.name} added at {branch.name}",
    )
    db.commit()
    return _location_read(db, principal, loc.id)


def update_location(
    db: Session, principal: Principal, location_id: uuid.UUID, body: LocationUpdate
) -> LocationRead:
    loc = _location(db, principal, location_id, active=False)
    principal.require(P.INVENTORY_ADJUST, loc.branch_id)
    loc.name = body.name
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"This branch already has a location named {body.name}.") from exc
    db.commit()
    return _location_read(db, principal, loc.id)


def set_location_archived(
    db: Session, principal: Principal, location_id: uuid.UUID, archived: bool
) -> LocationRead:
    loc = _location(db, principal, location_id, active=False)
    principal.require(P.INVENTORY_ADJUST, loc.branch_id)
    if archived:
        if loc.is_default:
            raise ConflictError("The branch's default location cannot be archived.")
        held = db.scalar(
            select(func.coalesce(func.sum(StockLevel.on_hand), 0)).where(
                StockLevel.location_id == loc.id
            )
        )
        if held:
            raise ConflictError(f"{loc.name} still holds stock. Transfer it out first.")
    loc.archived_at = utcnow() if archived else None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=loc.branch_id,
        actor=principal,
        action="stock_location.archived" if archived else "stock_location.restored",
        entity_type="stock_location",
        entity_id=loc.id,
        summary=f"Stock location {loc.name} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return _location_read(db, principal, loc.id)


def set_min_level(
    db: Session,
    principal: Principal,
    part_id: uuid.UUID,
    location_id: uuid.UUID,
    body: MinLevelUpdate,
) -> PartRead:
    part = _load_part(db, principal, part_id)
    loc = _location(db, principal, location_id)
    principal.require(P.INVENTORY_ADJUST, loc.branch_id)
    if body.min_quantity is not None:
        _check_whole(part, body.min_quantity)
    level = _lock_levels(db, [(loc, part.id)])[(loc.id, part.id)]
    before = level.min_quantity
    level.min_quantity = body.min_quantity
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=loc.branch_id,
        actor=principal,
        action="stock.min_level_set",
        entity_type="part",
        entity_id=part.id,
        summary=f"Minimum for {part.sku} at {loc.name} set to {body.min_quantity}",
        changes={"min_quantity": [before, body.min_quantity]},
    )
    db.commit()
    return read_part(db, principal, part)


# --------------------------------------------------------------------------- operations


def _lock_levels(
    db: Session, pairs: list[tuple[StockLocation, uuid.UUID]]
) -> dict[tuple[uuid.UUID, uuid.UUID], StockLevel]:
    """Create missing stock-level rows (at zero) and lock all of them in a fixed order."""
    keys = sorted(
        {(loc.id, part_id) for loc, part_id in pairs}, key=lambda k: (str(k[0]), str(k[1]))
    )
    locs = {loc.id: loc for loc, _ in pairs}
    for loc_id, part_id in keys:
        db.execute(
            insert(StockLevel)
            .values(
                location_id=loc_id,
                part_id=part_id,
                organisation_id=locs[loc_id].organisation_id,
                branch_id=locs[loc_id].branch_id,
            )
            .on_conflict_do_nothing()
        )
    levels: dict[tuple[uuid.UUID, uuid.UUID], StockLevel] = {}
    for loc_id, part_id in keys:
        level = db.scalar(
            select(StockLevel)
            .where(StockLevel.location_id == loc_id, StockLevel.part_id == part_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if level is None:  # pragma: no cover - inserted just above
            raise NotFoundError("Stock level missing.")
        levels[(loc_id, part_id)] = level
    return levels


def existing_operation(db: Session, organisation_id: uuid.UUID, key: str) -> StockOperation | None:
    return db.scalar(
        select(StockOperation).where(
            StockOperation.organisation_id == organisation_id,
            StockOperation.idempotency_key == key,
        )
    )


def start_operation(
    db: Session,
    principal: Principal,
    *,
    kind: str,
    key: str,
    print_: str,
    reason: str | None = None,
    reference: str | None = None,
    job_card_id: uuid.UUID | None = None,
) -> StockOperation | None:
    """Insert the operation row. Returns None if a concurrent request with the same key
    won; the caller then replays it."""
    op = StockOperation(
        organisation_id=principal.organisation_id,
        kind=kind,
        reason=reason,
        reference=reference,
        job_card_id=job_card_id,
        idempotency_key=key,
        request_fingerprint=print_,
        created_by_user_id=principal.user_id,
    )
    db.add(op)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return op


def replay(db: Session, principal: Principal, key: str, print_: str) -> OperationRead | None:
    existing = existing_operation(db, principal.organisation_id, key)
    if existing is None:
        return None
    check_replay(existing.request_fingerprint, print_)
    return operation_read(db, principal, existing)


def record_movement(
    db: Session,
    principal: Principal,
    op: StockOperation,
    loc: StockLocation,
    part: Part,
    kind: str,
    quantity: Decimal,
    *,
    unit_cost: Decimal | None = None,
    job_card_id: uuid.UUID | None = None,
) -> StockMovement:
    movement = StockMovement(
        organisation_id=op.organisation_id,
        branch_id=loc.branch_id,
        operation_id=op.id,
        location_id=loc.id,
        part_id=part.id,
        kind=kind,
        quantity=quantity,
        unit_cost=part.cost_price if unit_cost is None else unit_cost,
        job_card_id=job_card_id,
        created_by_user_id=principal.user_id,
    )
    db.add(movement)
    db.flush()  # fires the ledger trigger
    return movement


def adjust(
    db: Session, principal: Principal, body: AdjustmentCreate, key: str
) -> tuple[OperationRead, bool]:
    print_ = fingerprint({"op": "adjustment", **body.model_dump(mode="json")})
    if (done := replay(db, principal, key, print_)) is not None:
        return done, False
    loc = _location(db, principal, body.location_id)
    principal.require(P.INVENTORY_ADJUST, loc.branch_id)
    parts = _parts(db, principal, [line.part_id for line in body.lines])
    for line in body.lines:
        _check_whole(
            parts[line.part_id],
            line.counted if line.counted is not None else abs(line.change or ZERO),
        )

    op = start_operation(
        db, principal, kind="adjustment", key=key, print_=print_, reason=body.reason
    )
    if op is None:
        return replay(db, principal, key, print_), False  # type: ignore[return-value]
    levels = _lock_levels(db, [(loc, pid) for pid in parts])
    had_movements = set(
        db.scalars(
            select(StockMovement.part_id).where(
                StockMovement.location_id == loc.id, StockMovement.part_id.in_(list(parts))
            )
        )
    )
    unchanged: list[uuid.UUID] = []
    summary: list[str] = []
    for line in body.lines:
        part = parts[line.part_id]
        level = levels[(loc.id, part.id)]
        delta = (
            (line.counted - level.on_hand) if line.counted is not None else (line.change or ZERO)
        )
        if delta == 0:
            unchanged.append(part.id)
            continue
        new = level.on_hand + delta
        if new < 0:
            raise ConflictError(
                f"{part.sku}: only {level.on_hand} on hand at {loc.name}.",
                details={"part_id": str(part.id), "on_hand": str(level.on_hand)},
            )
        if new < level.reserved:
            raise ConflictError(
                f"{part.sku}: {level.reserved} is reserved for jobs at {loc.name}. "
                "Release reservations first.",
                details={"part_id": str(part.id), "reserved": str(level.reserved)},
            )
        kind = "adjustment" if part.id in had_movements else "opening"
        record_movement(db, principal, op, loc, part, kind, delta)
        summary.append(f"{part.sku} {delta:+}")
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=loc.branch_id,
        actor=principal,
        action="stock.adjusted",
        entity_type="stock_operation",
        entity_id=op.id,
        summary=f"Stock adjusted at {loc.name}: {', '.join(summary) or 'no changes'} "
        f"({body.reason})",
    )
    db.commit()
    result = operation_read(db, principal, op)
    result.unchanged_part_ids = unchanged
    return result, True


def transfer(
    db: Session, principal: Principal, body: TransferCreate, key: str
) -> tuple[OperationRead, bool]:
    print_ = fingerprint({"op": "transfer", **body.model_dump(mode="json")})
    if (done := replay(db, principal, key, print_)) is not None:
        return done, False
    if body.from_location_id == body.to_location_id:
        raise ConflictError("Choose two different locations.")
    src = _location(db, principal, body.from_location_id)
    dst = _location(db, principal, body.to_location_id)
    principal.require(P.INVENTORY_TRANSFER, src.branch_id)
    principal.require(P.INVENTORY_TRANSFER, dst.branch_id)
    parts = _parts(db, principal, [line.part_id for line in body.lines])
    for line in body.lines:
        _check_whole(parts[line.part_id], line.quantity)

    op = start_operation(db, principal, kind="transfer", key=key, print_=print_, reason=body.reason)
    if op is None:
        return replay(db, principal, key, print_), False  # type: ignore[return-value]
    levels = _lock_levels(db, [(loc, pid) for pid in parts for loc in (src, dst)])
    for line in body.lines:
        part = parts[line.part_id]
        level = levels[(src.id, part.id)]
        available = level.on_hand - level.reserved
        if line.quantity > available:
            raise ConflictError(
                f"{part.sku}: only {available} available at {src.name}.",
                details={"part_id": str(part.id), "available": str(available)},
            )
        record_movement(db, principal, op, src, part, "transfer_out", -line.quantity)
        record_movement(db, principal, op, dst, part, "transfer_in", line.quantity)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=src.branch_id,
        actor=principal,
        action="stock.transferred",
        entity_type="stock_operation",
        entity_id=op.id,
        summary=f"Stock moved from {src.name} to {dst.name}: "
        + ", ".join(f"{parts[ln.part_id].sku} {ln.quantity}" for ln in body.lines),
    )
    db.commit()
    return operation_read(db, principal, op), True


# --------------------------------------------------------------------------- movements


def _movement_rows(db: Session, conditions: list[Any]) -> Any:
    return (
        select(
            StockMovement,
            Part.name,
            Part.sku,
            StockLocation.name,
            Branch.name,
            User.full_name,
            StockOperation.reason,
            StockOperation.reference,
            JobCard.job_number,
        )
        .join(Part, Part.id == StockMovement.part_id)
        .join(StockLocation, StockLocation.id == StockMovement.location_id)
        .join(Branch, Branch.id == StockMovement.branch_id)
        .join(User, User.id == StockMovement.created_by_user_id)
        .join(StockOperation, StockOperation.id == StockMovement.operation_id)
        .outerjoin(JobCard, JobCard.id == StockMovement.job_card_id)
        .where(*conditions)
    )


def _movement_read(row: Any, costs: bool) -> MovementRead:
    m, part_name, sku, loc_name, branch_name, user, reason, reference, job_number = row
    return MovementRead(
        id=m.id,
        operation_id=m.operation_id,
        kind=m.kind,
        part=Ref(id=m.part_id, name=part_name),
        sku=sku,
        location=Ref(id=m.location_id, name=loc_name),
        branch=Ref(id=m.branch_id, name=branch_name),
        quantity=m.quantity,
        balance_after=m.balance_after,
        unit_cost=m.unit_cost if costs else None,
        job_card=Ref(id=m.job_card_id, name=job_number) if m.job_card_id else None,
        reason=reason,
        reference=reference,
        created_by=user,
        created_at=m.created_at,
    )


def operation_read(db: Session, principal: Principal, op: StockOperation) -> OperationRead:
    rows = db.execute(
        _movement_rows(db, [StockMovement.operation_id == op.id]).order_by(
            StockMovement.created_at, StockMovement.id
        )
    ).all()
    costs = can_see_costs(principal)
    return OperationRead(
        id=op.id,
        kind=op.kind,
        reason=op.reason,
        created_at=op.created_at,
        movements=[_movement_read(r, costs) for r in rows],
    )


def list_movements(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    part_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    kind: str | None = None,
    job_card_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[MovementRead], int]:
    branches = visible_branches(principal)
    conditions: list[Any] = [
        StockMovement.organisation_id == principal.organisation_id,
        *_in(StockMovement.branch_id, branches),
    ]
    for column, value in (
        (StockMovement.part_id, part_id),
        (StockMovement.location_id, location_id),
        (StockMovement.branch_id, branch_id),
        (StockMovement.kind, kind),
        (StockMovement.job_card_id, job_card_id),
    ):
        if value is not None:
            conditions.append(column == value)
    if date_from:
        conditions.append(StockMovement.created_at >= date_from)
    if date_to:
        conditions.append(StockMovement.created_at < date_to)
    total = db.scalar(select(func.count()).select_from(StockMovement).where(*conditions)) or 0
    rows = db.execute(
        _movement_rows(db, conditions)
        .order_by(StockMovement.created_at.desc(), StockMovement.id)
        .limit(params.page_size)
        .offset(params.offset)
    ).all()
    costs = can_see_costs(principal)
    return [_movement_read(r, costs) for r in rows], total
