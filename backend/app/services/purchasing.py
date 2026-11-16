"""Suppliers, purchase orders, goods received notes and supplier returns (CLAUDE.md §3.8).

Lifecycle: draft -> approved -> partially_received -> received. A draft or an approved
order with nothing received can be cancelled; an order that will not be completed can be
closed short with a reason.

- Receiving never exceeds what was ordered; each delivery is a goods received note whose
  lines add stock through the movement ledger at the order line's cost.
- Receiving updates the part's cost price to the latest received cost and the supplier's
  last cost for that part (stock is valued at cost price; see docs).
- Supplier returns are limited to what was received on the line, net of earlier returns,
  and to the free stock at the chosen location.
- Receiving and returns need an Idempotency-Key; the order row is locked while they run.
"""

import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.time import utcnow
from app.models import (
    Branch,
    GoodsReceivedLine,
    GoodsReceivedNote,
    OrganisationSettings,
    Part,
    PurchaseOrder,
    PurchaseOrderLine,
    StockLocation,
    StockMovement,
    Supplier,
    SupplierPart,
    SupplierReturn,
    SupplierReturnLine,
    User,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.job_card import Ref
from app.schemas.purchasing import (
    CloseRequest,
    GrnLineRead,
    GrnRead,
    PoCapabilities,
    PoCreate,
    PoDraftUpdate,
    PoLineInput,
    PoLineRead,
    PoListItem,
    PoRead,
    ReceiveRequest,
    ReceiveResult,
    SupplierCreate,
    SupplierListItem,
    SupplierPartInput,
    SupplierPartRead,
    SupplierRead,
    SupplierReturnCreate,
    SupplierReturnRead,
    SupplierUpdate,
    VersionBody,
)
from app.services import audit, numbering
from app.services.common import get_scoped
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
from app.services.invoices import today
from app.services.job_cards import StaleVersionError

ZERO = Decimal("0.00")
OPEN = ("approved", "partially_received")


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _names(db: Session, ids: list[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all())


def _visible_branches(principal: Principal) -> set[uuid.UUID] | None:
    branches = principal.branch_ids_with(P.SUPPLIERS_VIEW)
    if branches is not None and not branches:
        raise PermissionDeniedError("You do not have permission to view purchasing.")
    return branches


# --------------------------------------------------------------------------- suppliers


def _open_orders(db: Session, supplier_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not supplier_ids:
        return {}
    return dict(
        db.execute(
            select(PurchaseOrder.supplier_id, func.count())
            .where(PurchaseOrder.supplier_id.in_(supplier_ids), PurchaseOrder.status.in_(OPEN))
            .group_by(PurchaseOrder.supplier_id)
        ).all()
    )


def _supplier_item(s: Supplier, open_orders: int) -> SupplierListItem:
    return SupplierListItem(
        id=s.id,
        name=s.name,
        contact_person=s.contact_person,
        phone=s.phone,
        email=s.email,
        archived_at=s.archived_at,
        open_orders=open_orders,
    )


def list_suppliers(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    search: str | None = None,
    include_archived: bool = False,
) -> tuple[list[SupplierListItem], int]:
    _visible_branches(principal)
    conditions: list[Any] = [Supplier.organisation_id == principal.organisation_id]
    if not include_archived:
        conditions.append(Supplier.archived_at.is_(None))
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(Supplier.name.ilike(term), Supplier.contact_person.ilike(term)))
    total = db.scalar(select(func.count()).select_from(Supplier).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(Supplier)
            .where(*conditions)
            .order_by(Supplier.name)
            .limit(params.page_size)
            .offset(params.offset)
        )
    )
    counts = _open_orders(db, [s.id for s in rows])
    return [_supplier_item(s, counts.get(s.id, 0)) for s in rows], total


def read_supplier(db: Session, principal: Principal, s: Supplier) -> SupplierRead:
    branches = _visible_branches(principal)
    parts = db.execute(
        select(SupplierPart, Part)
        .join(Part, Part.id == SupplierPart.part_id)
        .where(SupplierPart.supplier_id == s.id)
        .order_by(Part.sku)
    ).all()
    since = utcnow() - timedelta(days=90)
    received = db.scalar(
        select(func.coalesce(func.sum(GoodsReceivedNote.total), 0))
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceivedNote.purchase_order_id)
        .where(
            PurchaseOrder.supplier_id == s.id,
            GoodsReceivedNote.received_at >= since,
            *([] if branches is None else [GoodsReceivedNote.branch_id.in_(branches)]),
        )
    )
    manage = principal.can(P.SUPPLIERS_MANAGE)
    return SupplierRead(
        **_supplier_item(s, _open_orders(db, [s.id]).get(s.id, 0)).model_dump(),
        address=s.address,
        tax_number=s.tax_number,
        account_number=s.account_number,
        payment_terms_days=s.payment_terms_days,
        notes=s.notes,
        parts=[
            SupplierPartRead(
                part=Ref(id=p.id, name=p.name),
                sku=p.sku,
                unit=p.unit,  # type: ignore[arg-type]
                supplier_sku=sp.supplier_sku,
                last_cost=sp.last_cost,
                lead_time_days=sp.lead_time_days,
            )
            for sp, p in parts
        ],
        received_value_90_days=received or ZERO,
        capabilities={"edit": manage, "archive": manage},
    )


def _supplier(db: Session, principal: Principal, supplier_id: uuid.UUID) -> Supplier:
    _visible_branches(principal)
    return get_scoped(db, Supplier, supplier_id, principal.organisation_id)


def get_supplier(db: Session, principal: Principal, supplier_id: uuid.UUID) -> SupplierRead:
    return read_supplier(db, principal, _supplier(db, principal, supplier_id))


def _flush_supplier(db: Session, name: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"A supplier named {name} already exists.", details={"field": "name"}
        ) from exc


def create_supplier(db: Session, principal: Principal, body: SupplierCreate) -> SupplierRead:
    principal.require(P.SUPPLIERS_MANAGE)
    s = Supplier(organisation_id=principal.organisation_id, **body.model_dump())
    db.add(s)
    _flush_supplier(db, body.name)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="supplier.created",
        entity_type="supplier",
        entity_id=s.id,
        summary=f"Supplier {s.name} added",
    )
    db.commit()
    return read_supplier(db, principal, s)


def update_supplier(
    db: Session, principal: Principal, supplier_id: uuid.UUID, body: SupplierUpdate
) -> SupplierRead:
    principal.require(P.SUPPLIERS_MANAGE)
    s = get_scoped(db, Supplier, supplier_id, principal.organisation_id)
    changes = body.changes()
    before = {k: getattr(s, k) for k in changes}
    for k, v in changes.items():
        setattr(s, k, v)
    _flush_supplier(db, s.name)
    diff = audit.diff(before, changes)
    if diff:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="supplier.updated",
            entity_type="supplier",
            entity_id=s.id,
            summary=f"Supplier {s.name} updated: {', '.join(sorted(diff))}",
            changes=diff,
        )
    db.commit()
    return read_supplier(db, principal, s)


def set_supplier_archived(
    db: Session, principal: Principal, supplier_id: uuid.UUID, archived: bool
) -> SupplierRead:
    principal.require(P.SUPPLIERS_MANAGE)
    s = get_scoped(db, Supplier, supplier_id, principal.organisation_id)
    if archived and _open_orders(db, [s.id]).get(s.id):
        raise ConflictError(
            f"{s.name} has open purchase orders. Receive, close or cancel them first."
        )
    s.archived_at = utcnow() if archived else None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="supplier.archived" if archived else "supplier.restored",
        entity_type="supplier",
        entity_id=s.id,
        summary=f"Supplier {s.name} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return read_supplier(db, principal, s)


def set_supplier_part(
    db: Session,
    principal: Principal,
    supplier_id: uuid.UUID,
    part_id: uuid.UUID,
    body: SupplierPartInput,
) -> SupplierRead:
    principal.require(P.SUPPLIERS_MANAGE)
    s = get_scoped(db, Supplier, supplier_id, principal.organisation_id)
    part = get_scoped(db, Part, part_id, principal.organisation_id)
    db.execute(
        insert(SupplierPart)
        .values(
            id=uuid.uuid4(),
            organisation_id=s.organisation_id,
            supplier_id=s.id,
            part_id=part.id,
            **body.model_dump(),
        )
        .on_conflict_do_update(
            index_elements=["supplier_id", "part_id"],
            set_={**body.model_dump(), "updated_at": func.now()},
        )
    )
    db.commit()
    return read_supplier(db, principal, s)


def remove_supplier_part(
    db: Session, principal: Principal, supplier_id: uuid.UUID, part_id: uuid.UUID
) -> SupplierRead:
    principal.require(P.SUPPLIERS_MANAGE)
    s = get_scoped(db, Supplier, supplier_id, principal.organisation_id)
    db.query(SupplierPart).filter(
        SupplierPart.supplier_id == s.id, SupplierPart.part_id == part_id
    ).delete()
    db.commit()
    return read_supplier(db, principal, s)


# --------------------------------------------------------------------------- orders: reads


def _load_po(
    db: Session, principal: Principal, po_id: uuid.UUID, *, lock: bool = False
) -> PurchaseOrder:
    stmt = select(PurchaseOrder).where(
        PurchaseOrder.id == po_id, PurchaseOrder.organisation_id == principal.organisation_id
    )
    if lock:
        stmt = stmt.with_for_update()
    po = db.scalar(stmt)
    if po is None or not principal.can(P.SUPPLIERS_VIEW, po.branch_id):
        raise NotFoundError("Purchase order not found.")
    return po


def _is_overdue(po: PurchaseOrder, on: Any) -> bool:
    return po.status in OPEN and po.expected_date is not None and po.expected_date < on


def _list_item(db: Session, po: PurchaseOrder, supplier: str, branch: str, on: Any) -> PoListItem:
    return PoListItem(
        id=po.id,
        po_number=po.po_number,
        status=po.status,  # type: ignore[arg-type]
        supplier=Ref(id=po.supplier_id, name=supplier),
        branch=Ref(id=po.branch_id, name=branch),
        expected_date=po.expected_date,
        is_overdue=_is_overdue(po, on),
        total=po.total,
        currency_code=po.currency_code,
        created_at=po.created_at,
    )


def list_orders(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    status: str | None = None,
    supplier_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[PoListItem], int]:
    branches = _visible_branches(principal)
    conditions: list[Any] = [PurchaseOrder.organisation_id == principal.organisation_id]
    if branches is not None:
        conditions.append(PurchaseOrder.branch_id.in_(branches))
    if status == "open":
        conditions.append(PurchaseOrder.status.in_(OPEN))
    elif status == "done":
        conditions.append(PurchaseOrder.status.in_(("received", "closed", "cancelled")))
    elif status:
        conditions.append(PurchaseOrder.status == status)
    if supplier_id:
        conditions.append(PurchaseOrder.supplier_id == supplier_id)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                PurchaseOrder.po_number.ilike(term),
                PurchaseOrder.supplier_id.in_(select(Supplier.id).where(Supplier.name.ilike(term))),
            )
        )
    base = (
        select(PurchaseOrder, Supplier.name, Branch.name)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .join(Branch, Branch.id == PurchaseOrder.branch_id)
        .where(*conditions)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(PurchaseOrder.created_at.desc()).limit(params.page_size).offset(params.offset)
    ).all()
    on = today(db, principal.organisation_id)
    return [_list_item(db, po, s, b, on) for po, s, b in rows], total


def read_order(db: Session, principal: Principal, po: PurchaseOrder) -> PoRead:
    supplier = db.scalar(select(Supplier.name).where(Supplier.id == po.supplier_id)) or ""
    branch = db.scalar(select(Branch.name).where(Branch.id == po.branch_id)) or ""
    base = _list_item(db, po, supplier, branch, today(db, po.organisation_id))
    lines = db.execute(
        select(PurchaseOrderLine, Part)
        .join(Part, Part.id == PurchaseOrderLine.part_id)
        .where(PurchaseOrderLine.purchase_order_id == po.id)
        .order_by(PurchaseOrderLine.position)
    ).all()
    parts = {p.id: p for _, p in lines}

    grns = list(
        db.scalars(
            select(GoodsReceivedNote)
            .where(GoodsReceivedNote.purchase_order_id == po.id)
            .order_by(GoodsReceivedNote.received_at)
        )
    )
    grn_lines: dict[uuid.UUID, list[GoodsReceivedLine]] = {}
    for gl in db.scalars(
        select(GoodsReceivedLine).where(GoodsReceivedLine.grn_id.in_([g.id for g in grns]))
    ):
        grn_lines.setdefault(gl.grn_id, []).append(gl)
    returns = list(
        db.scalars(
            select(SupplierReturn)
            .where(SupplierReturn.purchase_order_id == po.id)
            .order_by(SupplierReturn.created_at)
        )
    )
    ret_lines: dict[uuid.UUID, list[SupplierReturnLine]] = {}
    for rl in db.scalars(
        select(SupplierReturnLine).where(
            SupplierReturnLine.supplier_return_id.in_([r.id for r in returns])
        )
    ):
        ret_lines.setdefault(rl.supplier_return_id, []).append(rl)
    loc_ids = {g.location_id for g in grns} | {r.location_id for r in returns}
    loc_names = (
        dict(
            db.execute(
                select(StockLocation.id, StockLocation.name).where(StockLocation.id.in_(loc_ids))
            ).all()
        )
        if loc_ids
        else {}
    )
    names = _names(
        db,
        [
            po.created_by_user_id,
            po.approved_by_user_id,
            *(g.received_by_user_id for g in grns),
            *(r.created_by_user_id for r in returns),
        ],
    )

    def line_read(
        part_id: uuid.UUID, qty: Decimal, cost: Decimal, discrepancy: str | None
    ) -> GrnLineRead:
        p = parts.get(part_id) or db.get_one(Part, part_id)
        return GrnLineRead(
            part=Ref(id=p.id, name=p.name),
            sku=p.sku,
            quantity=qty,
            unit_cost=cost,
            discrepancy=discrepancy,
        )

    locations = db.execute(
        select(StockLocation.id, StockLocation.name)
        .where(StockLocation.branch_id == po.branch_id, StockLocation.archived_at.is_(None))
        .order_by(StockLocation.is_default.desc(), StockLocation.name)
    ).all()
    manage = principal.can(P.PURCHASING_MANAGE, po.branch_id)
    receive = principal.can(P.PURCHASING_RECEIVE, po.branch_id)
    anything_received = any(line.quantity_received > 0 for line, _ in lines)
    return PoRead(
        **base.model_dump(),
        notes=po.notes,
        received_value=sum((g.total for g in grns), ZERO),
        returned_value=sum((r.total for r in returns), ZERO),
        lines=[
            PoLineRead(
                id=line.id,
                part=Ref(id=p.id, name=p.name),
                sku=p.sku,
                unit=p.unit,  # type: ignore[arg-type]
                supplier_sku=line.supplier_sku,
                quantity_ordered=line.quantity_ordered,
                quantity_received=line.quantity_received,
                quantity_returned=line.quantity_returned,
                outstanding=line.quantity_ordered - line.quantity_received,
                unit_cost=line.unit_cost,
                line_total=line.line_total,
            )
            for line, p in lines
        ],
        receipts=[
            GrnRead(
                id=g.id,
                grn_number=g.grn_number,
                location=Ref(id=g.location_id, name=loc_names.get(g.location_id, "")),
                received_at=g.received_at,
                received_by=names.get(g.received_by_user_id, ""),
                delivery_reference=g.delivery_reference,
                supplier_invoice_reference=g.supplier_invoice_reference,
                notes=g.notes,
                total=g.total,
                lines=[
                    line_read(x.part_id, x.quantity, x.unit_cost, x.discrepancy)
                    for x in grn_lines.get(g.id, [])
                ],
            )
            for g in grns
        ],
        returns=[
            SupplierReturnRead(
                id=r.id,
                location=Ref(id=r.location_id, name=loc_names.get(r.location_id, "")),
                reason=r.reason,
                reference=r.reference,
                total=r.total,
                created_by=names.get(r.created_by_user_id, ""),
                created_at=r.created_at,
                lines=[
                    line_read(x.part_id, x.quantity, x.unit_cost, None)
                    for x in ret_lines.get(r.id, [])
                ],
            )
            for r in returns
        ],
        created_by=names.get(po.created_by_user_id, ""),
        approved_by=names.get(po.approved_by_user_id) if po.approved_by_user_id else None,
        approved_at=po.approved_at,
        closed_reason=po.closed_reason,
        version=po.version,
        locations=[Ref(id=i, name=n) for i, n in locations],
        capabilities=PoCapabilities(
            edit=manage and po.status == "draft",
            approve=po.status == "draft"
            and bool(lines)
            and principal.can(P.PURCHASING_APPROVE, po.branch_id),
            receive=receive and po.status in OPEN,
            return_goods=receive and anything_received,
            cancel=manage
            and (po.status == "draft" or (po.status == "approved" and not anything_received)),
            close=manage and po.status == "partially_received",
        ),
    )


def get_order(db: Session, principal: Principal, po_id: uuid.UUID) -> PoRead:
    return read_order(db, principal, _load_po(db, principal, po_id))


# --------------------------------------------------------------------------- orders: drafts


def _priced_lines(
    db: Session, principal: Principal, supplier_id: uuid.UUID, lines: list[PoLineInput]
) -> list[dict[str, Any]]:
    parts = load_parts(db, principal, [line.part_id for line in lines])
    refs = {
        sp.part_id: sp
        for sp in db.scalars(
            select(SupplierPart).where(
                SupplierPart.supplier_id == supplier_id, SupplierPart.part_id.in_(list(parts))
            )
        )
    }
    out = []
    for pos, line in enumerate(lines):
        part = parts[line.part_id]
        check_whole(part, line.quantity)
        ref = refs.get(part.id)
        cost = line.unit_cost
        if cost is None:
            cost = ref.last_cost if ref and ref.last_cost is not None else part.cost_price
        out.append(
            {
                "position": pos,
                "part_id": part.id,
                "supplier_sku": ref.supplier_sku if ref else None,
                "quantity_ordered": line.quantity,
                "unit_cost": cost,
                "line_total": _cents(line.quantity * cost),
            }
        )
    return out


def _replace_lines(db: Session, po: PurchaseOrder, priced: list[dict[str, Any]]) -> None:
    db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == po.id).delete()
    db.add_all(
        PurchaseOrderLine(organisation_id=po.organisation_id, purchase_order_id=po.id, **p)
        for p in priced
    )
    po.total = sum((p["line_total"] for p in priced), ZERO)


def create_order(db: Session, principal: Principal, body: PoCreate) -> PoRead:
    branch = get_scoped(db, Branch, body.branch_id, principal.organisation_id)
    principal.require(P.PURCHASING_MANAGE, branch.id)
    supplier = get_scoped(db, Supplier, body.supplier_id, principal.organisation_id)
    if supplier.archived_at:
        raise ConflictError(f"{supplier.name} is archived.")
    priced = _priced_lines(db, principal, supplier.id, body.lines)
    currency = db.scalar(
        select(OrganisationSettings.currency_code).where(
            OrganisationSettings.organisation_id == principal.organisation_id
        )
    )
    po = PurchaseOrder(
        organisation_id=principal.organisation_id,
        branch_id=branch.id,
        supplier_id=supplier.id,
        po_number=numbering.allocate(
            db, principal.organisation_id, numbering.DocumentType.PURCHASE_ORDER
        ),
        status="draft",
        currency_code=currency or "NAD",
        expected_date=body.expected_date,
        notes=body.notes,
        created_by_user_id=principal.user_id,
    )
    db.add(po)
    db.flush()
    _replace_lines(db, po, priced)
    audit.record(
        db,
        organisation_id=po.organisation_id,
        branch_id=po.branch_id,
        actor=principal,
        action="purchase_order.created",
        entity_type="purchase_order",
        entity_id=po.id,
        summary=f"Purchase order {po.po_number} started for {supplier.name}",
    )
    db.commit()
    return read_order(db, principal, po)


def _check_version(po: PurchaseOrder, version: int) -> None:
    if po.version != version:
        raise StaleVersionError("This purchase order was changed by someone else. Reload it.")


def save_draft(db: Session, principal: Principal, po_id: uuid.UUID, body: PoDraftUpdate) -> PoRead:
    po = _load_po(db, principal, po_id, lock=True)
    principal.require(P.PURCHASING_MANAGE, po.branch_id)
    if po.status != "draft":
        raise ConflictError("Only draft purchase orders can be edited.")
    _check_version(po, body.version)
    _replace_lines(db, po, _priced_lines(db, principal, po.supplier_id, body.lines))
    po.expected_date, po.notes = body.expected_date, body.notes
    po.version += 1
    db.commit()
    return read_order(db, principal, po)


def approve(db: Session, principal: Principal, po_id: uuid.UUID, body: VersionBody) -> PoRead:
    po = _load_po(db, principal, po_id, lock=True)
    principal.require(P.PURCHASING_APPROVE, po.branch_id)
    if po.status != "draft":
        raise ConflictError("Only draft purchase orders can be approved.")
    _check_version(po, body.version)
    if not db.scalar(
        select(func.count())
        .select_from(PurchaseOrderLine)
        .where(PurchaseOrderLine.purchase_order_id == po.id)
    ):
        raise ConflictError("Add at least one line before approving.")
    po.status, po.approved_at, po.approved_by_user_id = "approved", utcnow(), principal.user_id
    po.version += 1
    audit.record(
        db,
        organisation_id=po.organisation_id,
        branch_id=po.branch_id,
        actor=principal,
        action="purchase_order.approved",
        entity_type="purchase_order",
        entity_id=po.id,
        summary=f"Purchase order {po.po_number} approved for {po.currency_code} {po.total}",
    )
    db.commit()
    return read_order(db, principal, po)


def cancel(db: Session, principal: Principal, po_id: uuid.UUID, body: CloseRequest) -> PoRead:
    po = _load_po(db, principal, po_id, lock=True)
    principal.require(P.PURCHASING_MANAGE, po.branch_id)
    _check_version(po, body.version)
    received = db.scalar(
        select(func.coalesce(func.sum(PurchaseOrderLine.quantity_received), 0)).where(
            PurchaseOrderLine.purchase_order_id == po.id
        )
    )
    if po.status not in ("draft", "approved") or received:
        raise ConflictError("Only orders with nothing received can be cancelled. Close it instead.")
    po.status, po.closed_reason, po.closed_at = "cancelled", body.reason, utcnow()
    po.version += 1
    audit.record(
        db,
        organisation_id=po.organisation_id,
        branch_id=po.branch_id,
        actor=principal,
        action="purchase_order.cancelled",
        entity_type="purchase_order",
        entity_id=po.id,
        summary=f"Purchase order {po.po_number} cancelled: {body.reason}",
    )
    db.commit()
    return read_order(db, principal, po)


def close(db: Session, principal: Principal, po_id: uuid.UUID, body: CloseRequest) -> PoRead:
    po = _load_po(db, principal, po_id, lock=True)
    principal.require(P.PURCHASING_MANAGE, po.branch_id)
    _check_version(po, body.version)
    if po.status != "partially_received":
        raise ConflictError("Only partly received orders can be closed short.")
    po.status, po.closed_reason, po.closed_at = "closed", body.reason, utcnow()
    po.version += 1
    audit.record(
        db,
        organisation_id=po.organisation_id,
        branch_id=po.branch_id,
        actor=principal,
        action="purchase_order.closed",
        entity_type="purchase_order",
        entity_id=po.id,
        summary=f"Purchase order {po.po_number} closed short: {body.reason}",
    )
    db.commit()
    return read_order(db, principal, po)


# --------------------------------------------------------------------------- receiving


def _po_location(
    db: Session, principal: Principal, po: PurchaseOrder, location_id: uuid.UUID
) -> StockLocation:
    loc = get_location(db, principal, location_id)
    if loc.branch_id != po.branch_id:
        raise ConflictError("Use a stock location in the order's branch.")
    return loc


def _locked_lines(
    db: Session, po: PurchaseOrder, line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PurchaseOrderLine]:
    if len(set(line_ids)) != len(line_ids):
        raise ConflictError("Each order line may appear only once.")
    lines = {
        line.id: line
        for line in db.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == po.id, PurchaseOrderLine.id.in_(line_ids))
            .with_for_update()
        )
    }
    for lid in line_ids:
        if lid not in lines:
            raise NotFoundError("Order line not found.", details={"po_line_id": str(lid)})
    return lines


def _result(
    db: Session, principal: Principal, po: PurchaseOrder, operation_id: uuid.UUID
) -> ReceiveResult:
    rows = db.execute(
        movement_rows(db, [StockMovement.operation_id == operation_id]).order_by(
            StockMovement.created_at
        )
    ).all()
    costs = can_see_costs(principal)
    return ReceiveResult(
        order=read_order(db, principal, po), movements=[movement_read(r, costs) for r in rows]
    )


def _replay(
    db: Session, principal: Principal, po_id: uuid.UUID, key: str, print_: str
) -> ReceiveResult | None:
    existing = existing_operation(db, principal.organisation_id, key)
    if existing is None:
        return None
    check_replay(existing.request_fingerprint, print_)
    return _result(db, principal, _load_po(db, principal, po_id), existing.id)


def receive(
    db: Session, principal: Principal, po_id: uuid.UUID, body: ReceiveRequest, key: str
) -> tuple[ReceiveResult, bool]:
    print_ = fingerprint({"op": "receive", "po": str(po_id), **body.model_dump(mode="json")})
    if (done := _replay(db, principal, po_id, key, print_)) is not None:
        return done, False
    po = _load_po(db, principal, po_id, lock=True)
    principal.require(P.PURCHASING_RECEIVE, po.branch_id)
    if po.status not in OPEN:
        raise ConflictError("Only approved orders can be received.")
    loc = _po_location(db, principal, po, body.location_id)
    lines = _locked_lines(db, po, [ln.po_line_id for ln in body.lines])
    parts = {
        p.id: p
        for p in db.scalars(select(Part).where(Part.id.in_([ln.part_id for ln in lines.values()])))
    }
    for req in body.lines:
        line = lines[req.po_line_id]
        part = parts[line.part_id]
        check_whole(part, req.quantity)
        outstanding = line.quantity_ordered - line.quantity_received
        if req.quantity > outstanding:
            raise ConflictError(
                f"{part.sku}: only {outstanding} still to be received on this order.",
                details={"po_line_id": str(line.id), "outstanding": str(outstanding)},
            )

    grn_number = numbering.allocate(db, po.organisation_id, numbering.DocumentType.GOODS_RECEIVED)
    op = start_operation(
        db, principal, kind="receipt", key=key, print_=print_, reference=grn_number
    )
    if op is None:
        return _replay(db, principal, po_id, key, print_), False  # type: ignore[return-value]
    grn = GoodsReceivedNote(
        organisation_id=po.organisation_id,
        branch_id=po.branch_id,
        purchase_order_id=po.id,
        location_id=loc.id,
        operation_id=op.id,
        grn_number=grn_number,
        delivery_reference=body.delivery_reference,
        supplier_invoice_reference=body.supplier_invoice_reference,
        notes=body.notes,
        total=ZERO,
        received_by_user_id=principal.user_id,
    )
    db.add(grn)
    db.flush()
    lock_levels(db, [(loc, line.part_id) for line in lines.values()])
    cost_changes = []
    total = ZERO
    for req in body.lines:
        line = lines[req.po_line_id]
        part = parts[line.part_id]
        record_movement(
            db, principal, op, loc, part, "receipt", req.quantity, unit_cost=line.unit_cost
        )
        line.quantity_received += req.quantity
        db.add(
            GoodsReceivedLine(
                grn_id=grn.id,
                po_line_id=line.id,
                part_id=part.id,
                quantity=req.quantity,
                unit_cost=line.unit_cost,
                discrepancy=req.discrepancy,
            )
        )
        total += _cents(req.quantity * line.unit_cost)
        if part.cost_price != line.unit_cost:
            cost_changes.append(f"{part.sku} {part.cost_price} -> {line.unit_cost}")
            part.cost_price = line.unit_cost
        db.execute(
            insert(SupplierPart)
            .values(
                id=uuid.uuid4(),
                organisation_id=po.organisation_id,
                supplier_id=po.supplier_id,
                part_id=part.id,
                supplier_sku=line.supplier_sku,
                last_cost=line.unit_cost,
            )
            .on_conflict_do_update(
                index_elements=["supplier_id", "part_id"],
                set_={"last_cost": line.unit_cost, "updated_at": func.now()},
            )
        )
    grn.total = total
    db.flush()
    all_lines = list(
        db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id))
    )
    po.status = (
        "received"
        if all(x.quantity_received >= x.quantity_ordered for x in all_lines)
        else "partially_received"
    )
    po.version += 1
    audit.record(
        db,
        organisation_id=po.organisation_id,
        branch_id=po.branch_id,
        actor=principal,
        action="purchase_order.received",
        entity_type="purchase_order",
        entity_id=po.id,
        summary=f"{grn_number} received into {loc.name} against {po.po_number} "
        f"({po.currency_code} {total})"
        + (f"; cost prices updated: {', '.join(cost_changes)}" if cost_changes else ""),
    )
    db.commit()
    return _result(db, principal, po, op.id), True


def return_to_supplier(
    db: Session, principal: Principal, po_id: uuid.UUID, body: SupplierReturnCreate, key: str
) -> tuple[ReceiveResult, bool]:
    print_ = fingerprint(
        {"op": "supplier_return", "po": str(po_id), **body.model_dump(mode="json")}
    )
    if (done := _replay(db, principal, po_id, key, print_)) is not None:
        return done, False
    po = _load_po(db, principal, po_id, lock=True)
    principal.require(P.PURCHASING_RECEIVE, po.branch_id)
    loc = _po_location(db, principal, po, body.location_id)
    lines = _locked_lines(db, po, [ln.po_line_id for ln in body.lines])
    parts = {
        p.id: p
        for p in db.scalars(select(Part).where(Part.id.in_([ln.part_id for ln in lines.values()])))
    }
    for req in body.lines:
        line = lines[req.po_line_id]
        check_whole(parts[line.part_id], req.quantity)
        returnable = line.quantity_received - line.quantity_returned
        if req.quantity > returnable:
            raise ConflictError(
                f"{parts[line.part_id].sku}: only {returnable} received and not yet returned.",
                details={"po_line_id": str(line.id), "returnable": str(returnable)},
            )
    op = start_operation(
        db,
        principal,
        kind="supplier_return",
        key=key,
        print_=print_,
        reason=body.reason,
        reference=body.reference,
    )
    if op is None:
        return _replay(db, principal, po_id, key, print_), False  # type: ignore[return-value]
    levels = lock_levels(db, [(loc, line.part_id) for line in lines.values()])
    ret = SupplierReturn(
        organisation_id=po.organisation_id,
        purchase_order_id=po.id,
        location_id=loc.id,
        operation_id=op.id,
        reason=body.reason,
        reference=body.reference,
        total=ZERO,
        created_by_user_id=principal.user_id,
    )
    db.add(ret)
    db.flush()
    total = ZERO
    for req in body.lines:
        line = lines[req.po_line_id]
        part = parts[line.part_id]
        level = levels[(loc.id, part.id)]
        free = level.on_hand - level.reserved
        if req.quantity > free:
            raise ConflictError(
                f"{part.sku}: only {free} free at {loc.name}.",
                details={"part_id": str(part.id), "free": str(free)},
            )
        record_movement(
            db, principal, op, loc, part, "supplier_return", -req.quantity, unit_cost=line.unit_cost
        )
        line.quantity_returned += req.quantity
        db.add(
            SupplierReturnLine(
                supplier_return_id=ret.id,
                po_line_id=line.id,
                part_id=part.id,
                quantity=req.quantity,
                unit_cost=line.unit_cost,
            )
        )
        total += _cents(req.quantity * line.unit_cost)
    ret.total = total
    po.version += 1
    audit.record(
        db,
        organisation_id=po.organisation_id,
        branch_id=po.branch_id,
        actor=principal,
        action="purchase_order.returned",
        entity_type="purchase_order",
        entity_id=po.id,
        summary=f"Returned to supplier against {po.po_number} from {loc.name} "
        f"({po.currency_code} {total}): {body.reason}",
    )
    db.commit()
    return _result(db, principal, po, op.id), True
