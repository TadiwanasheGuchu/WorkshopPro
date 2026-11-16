"""Operational and financial reports (CLAUDE.md §3.13).

- Every report has an explicit period (inclusive local dates in the organisation's time
  zone) and is limited to the branches the caller may report on.
- Invoiced amounts, cash received and receivables are separate figures. Invoices issued
  are never presented as cash received.
- Receivables are as at today: they are balances now, not at the end of the period.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.time import utcnow
from app.models import (
    Branch,
    CreditNote,
    GoodsReceivedNote,
    Invoice,
    JobAssignment,
    JobCard,
    JobStatusHistory,
    OrganisationSettings,
    Part,
    PartCategory,
    Payment,
    PaymentAllocation,
    PurchaseOrder,
    PurchaseOrderLine,
    Quotation,
    QuotationDecision,
    QuotationVersion,
    StockLevel,
    StockLocation,
    StockMovement,
    SupplierReturn,
    User,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.job_card import Ref
from app.schemas.report import (
    AgeingRow,
    CategoryValue,
    CountAmount,
    DayRow,
    Definition,
    FinancialReport,
    InventoryReport,
    InvoicedTotals,
    LocationValue,
    MechanicRow,
    MethodRow,
    MovementSummary,
    OperationsReport,
    PartUsage,
    Period,
    PurchasingSummary,
    QuotationOutcomes,
    Receivables,
    Reconciliation,
    Valuation,
)
from app.services.job_workflow import TERMINAL, JobStatus

ZERO = Decimal("0.00")
MAX_DAYS = 366


class InvalidPeriodError(AppError):
    status_code = 422
    code = "invalid_period"


FINANCIAL_DEFINITIONS = [
    Definition(
        term="Invoiced",
        definition="Totals (incl. tax) of invoices issued in the period, by issue date. "
        "Drafts are excluded. This is revenue billed, not cash received.",
    ),
    Definition(
        term="Credited",
        definition="Credit notes issued in the period. Net invoiced = invoiced - credited.",
    ),
    Definition(
        term="Received",
        definition="Payments recorded as received in the period, by date received, "
        "whether or not they were applied to an invoice.",
    ),
    Definition(
        term="Refunded / reversed",
        definition="Money paid back to customers, and payments reversed because they were "
        "recorded in error, by the date of the refund or reversal.",
    ),
    Definition(
        term="Net received",
        definition="Received - refunded - reversed.",
    ),
    Definition(
        term="Outstanding",
        definition="Unpaid balances of issued invoices as at today "
        "(total - credited - paid), regardless of the period.",
    ),
    Definition(
        term="Overdue",
        definition="The part of outstanding on invoices whose due date has passed.",
    ),
    Definition(
        term="Unapplied credit",
        definition="Money received but not applied to any invoice, plus overpayments. "
        "Owed to customers or available for their next invoice.",
    ),
]

OPERATIONS_DEFINITIONS = [
    Definition(term="Received", definition="Job cards opened in the period, by received date."),
    Definition(
        term="Completed / cancelled",
        definition="Jobs moved to completed (vehicle collected) or cancelled in the period.",
    ),
    Definition(
        term="Turnaround",
        definition="Time from vehicle received to completed, for jobs completed in the period.",
    ),
    Definition(
        term="Open now / overdue now",
        definition="Jobs not completed or cancelled at this moment; overdue if the promised "
        "time has passed.",
    ),
    Definition(
        term="Quotations",
        definition="Versions sent in the period, and customer decisions recorded in the period. "
        "Approved value is the total of approved versions.",
    ),
    Definition(
        term="Mechanic workload",
        definition="Open jobs a mechanic is currently assigned to, and jobs completed in the "
        "period while assigned to them.",
    ),
]


def _settings(db: Session, organisation_id: uuid.UUID) -> OrganisationSettings:
    return db.get_one(OrganisationSettings, organisation_id)


def _bounds(date_from: date, date_to: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    if date_to < date_from:
        raise InvalidPeriodError("The end date is before the start date.")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise InvalidPeriodError(f"Choose a period of at most {MAX_DAYS} days.")
    start = datetime.combine(date_from, time.min, tzinfo=tz)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    return start, end


def _scope(
    db: Session, principal: Principal, permission: str, branch_id: uuid.UUID | None
) -> tuple[set[uuid.UUID] | None, Ref | None]:
    """Branches the report covers (None = all) and the selected branch, if any."""
    allowed = principal.branch_ids_with(permission)
    if allowed is not None and not allowed:
        raise PermissionDeniedError("You do not have permission to view this report.")
    if branch_id is None:
        return allowed, None
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id, Branch.organisation_id == principal.organisation_id
        )
    )
    if branch is None:
        raise NotFoundError("Branch not found.")
    if allowed is not None and branch_id not in allowed:
        raise PermissionDeniedError("You do not have permission to report on this branch.")
    return {branch_id}, Ref(id=branch.id, name=branch.name)


def _in(column: Any, branches: set[uuid.UUID] | None) -> list[Any]:
    return [] if branches is None else [column.in_(branches)]


# --------------------------------------------------------------------------- financial


def financial(
    db: Session,
    principal: Principal,
    date_from: date,
    date_to: date,
    branch_id: uuid.UUID | None = None,
) -> FinancialReport:
    s = _settings(db, principal.organisation_id)
    tz = ZoneInfo(s.timezone)
    start, end = _bounds(date_from, date_to, tz)
    branches, branch = _scope(db, principal, P.REPORTS_FINANCIAL, branch_id)
    org = principal.organisation_id

    inv_cond = [
        Invoice.organisation_id == org,
        Invoice.status == "issued",
        *_in(Invoice.branch_id, branches),
    ]
    count, subtotal, tax, total = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(Invoice.subtotal), 0),
            func.coalesce(func.sum(Invoice.tax_total), 0),
            func.coalesce(func.sum(Invoice.total), 0),
        ).where(*inv_cond, Invoice.issue_date.between(date_from, date_to))
    ).one()
    invoiced = InvoicedTotals(count=count, subtotal=subtotal, tax_total=tax, total=total)

    cn_count, cn_total = db.execute(
        select(func.count(), func.coalesce(func.sum(CreditNote.total), 0))
        .join(Invoice, Invoice.id == CreditNote.invoice_id)
        .where(
            CreditNote.organisation_id == org,
            CreditNote.issue_date.between(date_from, date_to),
            *_in(Invoice.branch_id, branches),
        )
    ).one()

    pay_cond = [
        Payment.organisation_id == org,
        Payment.received_at >= start,
        Payment.received_at < end,
        *_in(Payment.branch_id, branches),
    ]
    by_kind: dict[str, CountAmount] = {}
    methods: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"in": ZERO, "out": ZERO})
    for kind, method, n, amount in db.execute(
        select(Payment.kind, Payment.method, func.count(), func.sum(Payment.amount))
        .where(*pay_cond)
        .group_by(Payment.kind, Payment.method)
    ):
        prev = by_kind.get(kind, CountAmount(count=0, total=ZERO))
        by_kind[kind] = CountAmount(count=prev.count + n, total=prev.total + amount)
        methods[method]["in" if kind == "payment" else "out"] += amount
    zero = CountAmount(count=0, total=ZERO)
    received = by_kind.get("payment", zero)
    refunded = by_kind.get("refund", zero)
    reversed_ = by_kind.get("reversal", zero)

    local_day = func.date(func.timezone(s.timezone, Payment.received_at))
    days: dict[date, dict[str, Decimal]] = defaultdict(lambda: {"inv": ZERO, "rec": ZERO})
    for day, amount in db.execute(
        select(Invoice.issue_date, func.sum(Invoice.total))
        .where(*inv_cond, Invoice.issue_date.between(date_from, date_to))
        .group_by(Invoice.issue_date)
    ):
        days[day]["inv"] = amount
    for day, amount in db.execute(
        select(local_day, func.sum(Payment.amount))
        .where(*pay_cond, Payment.kind == "payment")
        .group_by(local_day)
    ):
        days[day]["rec"] = amount

    return FinancialReport(
        period=Period(date_from=date_from, date_to=date_to, timezone=s.timezone),
        branch=branch,
        currency_code=s.currency_code,
        invoiced=invoiced,
        credited=CountAmount(count=cn_count, total=cn_total),
        net_invoiced=invoiced.total - cn_total,
        received=received,
        refunded=refunded,
        reversed=reversed_,
        net_received=received.total - refunded.total - reversed_.total,
        by_method=[
            MethodRow(method=m, received=v["in"], paid_out=v["out"])
            for m, v in sorted(methods.items())
        ],
        daily=[
            DayRow(date=d, invoiced=v["inv"], received=v["rec"]) for d, v in sorted(days.items())
        ],
        receivables=_receivables(db, org, branches, utcnow().astimezone(tz).date()),
        definitions=FINANCIAL_DEFINITIONS,
    )


AGEING = [("Not yet due", None, 0), ("1-30 days", 1, 30), ("31-60 days", 31, 60)]
AGEING += [("61-90 days", 61, 90), ("Over 90 days", 91, None)]


def _receivables(
    db: Session, org: uuid.UUID, branches: set[uuid.UUID] | None, today: date
) -> Receivables:
    balance = Invoice.total - Invoice.amount_credited - Invoice.amount_paid
    cond = [
        Invoice.organisation_id == org,
        Invoice.status == "issued",
        *_in(Invoice.branch_id, branches),
    ]
    rows = db.execute(select(balance, Invoice.due_date).where(*cond, balance > 0)).all()
    buckets = {label: [0, ZERO] for label, _, _ in AGEING}
    overdue = ZERO
    for amount, due in rows:
        late = (today - due).days if due else 0
        if late > 0:
            overdue += amount
        for label, low, high in AGEING:
            if (low is None and late <= 0) or (
                low is not None and late >= low and (high is None or late <= high)
            ):
                buckets[label][0] += 1
                buckets[label][1] += amount
                break

    overpaid = (
        db.scalar(select(func.coalesce(func.sum(-balance), 0)).where(*cond, balance < 0)) or ZERO
    )
    allocated = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .where(PaymentAllocation.payment_id == Payment.id)
        .scalar_subquery()
    )
    reversal = Payment.__table__.alias("reversal")
    unallocated = (
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount - allocated), 0)).where(
                Payment.organisation_id == org,
                Payment.kind == "payment",
                ~exists().where(reversal.c.reverses_payment_id == Payment.id),
                *_in(Payment.branch_id, branches),
            )
        )
        or ZERO
    )
    return Receivables(
        as_at=today,
        outstanding=sum((a for a, _ in rows), ZERO),
        overdue=overdue,
        open_invoices=len(rows),
        ageing=[AgeingRow(bucket=k, count=v[0], amount=v[1]) for k, v in buckets.items()],
        unapplied_credit=unallocated + overpaid,
    )


# --------------------------------------------------------------------------- operations


def operations(
    db: Session,
    principal: Principal,
    date_from: date,
    date_to: date,
    branch_id: uuid.UUID | None = None,
) -> OperationsReport:
    s = _settings(db, principal.organisation_id)
    tz = ZoneInfo(s.timezone)
    start, end = _bounds(date_from, date_to, tz)
    branches, branch = _scope(db, principal, P.REPORTS_OPERATIONAL, branch_id)
    org = principal.organisation_id
    job_cond = [JobCard.organisation_id == org, *_in(JobCard.branch_id, branches)]

    received = db.scalar(
        select(func.count())
        .select_from(JobCard)
        .where(*job_cond, JobCard.received_at >= start, JobCard.received_at < end)
    )

    def moved_to(status: JobStatus) -> Any:
        return (
            select(JobStatusHistory.job_card_id, JobStatusHistory.changed_at)
            .join(JobCard, JobCard.id == JobStatusHistory.job_card_id)
            .where(
                *job_cond,
                JobStatusHistory.to_status == status.value,
                JobStatusHistory.changed_at >= start,
                JobStatusHistory.changed_at < end,
            )
        )

    completed_q = moved_to(JobStatus.COMPLETED).subquery()
    completed = db.scalar(select(func.count()).select_from(completed_q)) or 0
    cancelled = (
        db.scalar(select(func.count()).select_from(moved_to(JobStatus.CANCELLED).subquery())) or 0
    )
    hours = func.extract("epoch", completed_q.c.changed_at - JobCard.received_at) / 3600
    avg_h, median_h = db.execute(
        select(func.avg(hours), func.percentile_cont(0.5).within_group(hours))
        .select_from(completed_q)
        .join(JobCard, JobCard.id == completed_q.c.job_card_id)
    ).one()

    open_statuses = [st.value for st in JobStatus if st not in TERMINAL]
    by_status = dict(
        db.execute(
            select(JobCard.status, func.count())
            .where(*job_cond, JobCard.status.in_(open_statuses))
            .group_by(JobCard.status)
        ).all()
    )
    overdue = db.scalar(
        select(func.count())
        .select_from(JobCard)
        .where(*job_cond, JobCard.status.in_(open_statuses), JobCard.promised_at < utcnow())
    )

    q_cond = [Quotation.organisation_id == org, *_in(Quotation.branch_id, branches)]
    sent = db.scalar(
        select(func.count())
        .select_from(QuotationVersion)
        .join(Quotation, Quotation.id == QuotationVersion.quotation_id)
        .where(*q_cond, QuotationVersion.sent_at >= start, QuotationVersion.sent_at < end)
    )
    decisions = {
        d: (n, total)
        for d, n, total in db.execute(
            select(QuotationDecision.decision, func.count(), func.sum(QuotationDecision.total))
            .join(QuotationVersion, QuotationVersion.id == QuotationDecision.version_id)
            .join(Quotation, Quotation.id == QuotationVersion.quotation_id)
            .where(
                *q_cond,
                QuotationDecision.decided_at >= start,
                QuotationDecision.decided_at < end,
            )
            .group_by(QuotationDecision.decision)
        )
    }

    active = JobAssignment.unassigned_at.is_(None)
    open_by_user = dict(
        db.execute(
            select(JobAssignment.user_id, func.count())
            .join(JobCard, JobCard.id == JobAssignment.job_card_id)
            .where(*job_cond, active, JobCard.status.in_(open_statuses))
            .group_by(JobAssignment.user_id)
        ).all()
    )
    done_by_user = dict(
        db.execute(
            select(JobAssignment.user_id, func.count(func.distinct(JobAssignment.job_card_id)))
            .join(completed_q, completed_q.c.job_card_id == JobAssignment.job_card_id)
            .where(active)
            .group_by(JobAssignment.user_id)
        ).all()
    )
    user_ids = set(open_by_user) | set(done_by_user)
    names = (
        dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all())
        if user_ids
        else {}
    )

    return OperationsReport(
        period=Period(date_from=date_from, date_to=date_to, timezone=s.timezone),
        branch=branch,
        currency_code=s.currency_code,
        received=received or 0,
        completed=completed,
        cancelled=cancelled,
        turnaround_hours_avg=round(float(avg_h), 1) if avg_h is not None else None,
        turnaround_hours_median=round(float(median_h), 1) if median_h is not None else None,
        open_by_status={JobStatus(st): by_status.get(st, 0) for st in open_statuses},
        open_total=sum(by_status.values()),
        overdue_now=overdue or 0,
        quotations=QuotationOutcomes(
            sent=sent or 0,
            approved=decisions.get("approved", (0, ZERO))[0],
            rejected=decisions.get("rejected", (0, ZERO))[0],
            approved_value=decisions.get("approved", (0, ZERO))[1] or ZERO,
        ),
        mechanics=sorted(
            (
                MechanicRow(
                    user_id=u,
                    name=names.get(u, ""),
                    open_jobs=open_by_user.get(u, 0),
                    completed_in_period=done_by_user.get(u, 0),
                )
                for u in user_ids
            ),
            key=lambda r: (-r.open_jobs, r.name),
        ),
        definitions=OPERATIONS_DEFINITIONS,
    )


# --------------------------------------------------------------------------- inventory

INVENTORY_DEFINITIONS = [
    Definition(
        term="Stock value",
        definition="Quantity on hand x the part's current cost price, as at today. Cost price "
        "follows the last received purchase cost.",
    ),
    Definition(
        term="Movements",
        definition="Stock movements recorded in the period, by type. Value is quantity x the "
        "unit cost recorded on each movement (negative for stock going out).",
    ),
    Definition(
        term="Parts used",
        definition="Parts issued to jobs in the period, net of returns, at the cost recorded "
        "when issued.",
    ),
    Definition(
        term="Purchasing",
        definition="Orders approved in the period and their value; deliveries received and "
        "returns to suppliers in the period. Open orders are as at today: approved or partly "
        "received, valued at the cost of what is still outstanding. Amounts exclude tax.",
    ),
    Definition(
        term="Stock check",
        definition="As at today, every stock level is compared with the sum of its ledger "
        "movements, and reserved quantities with open reservations. Both should be zero.",
    ),
]


def _money(value: Decimal | None) -> Decimal:
    return (value or ZERO).quantize(Decimal("0.01"))


def inventory(
    db: Session,
    principal: Principal,
    date_from: date,
    date_to: date,
    branch_id: uuid.UUID | None = None,
) -> InventoryReport:
    s = _settings(db, principal.organisation_id)
    tz = ZoneInfo(s.timezone)
    start, end = _bounds(date_from, date_to, tz)
    branches, branch = _scope(db, principal, P.REPORTS_INVENTORY, branch_id)
    org = principal.organisation_id
    level_cond = [StockLevel.organisation_id == org, *_in(StockLevel.branch_id, branches)]
    value = StockLevel.on_hand * Part.cost_price

    by_location = [
        LocationValue(
            location=Ref(id=loc_id, name=loc_name),
            branch=Ref(id=b_id, name=b_name),
            units=units,
            value=_money(val),
        )
        for loc_id, loc_name, b_id, b_name, units, val in db.execute(
            select(
                StockLocation.id,
                StockLocation.name,
                Branch.id,
                Branch.name,
                func.sum(StockLevel.on_hand),
                func.sum(value),
            )
            .join(StockLocation, StockLocation.id == StockLevel.location_id)
            .join(Branch, Branch.id == StockLevel.branch_id)
            .join(Part, Part.id == StockLevel.part_id)
            .where(*level_cond, StockLevel.on_hand > 0)
            .group_by(StockLocation.id, StockLocation.name, Branch.id, Branch.name)
            .order_by(Branch.name, StockLocation.name)
        )
    ]
    by_category = [
        CategoryValue(category=name or "Uncategorised", parts=n, units=units, value=_money(val))
        for name, n, units, val in db.execute(
            select(
                PartCategory.name,
                func.count(func.distinct(Part.id)),
                func.sum(StockLevel.on_hand),
                func.sum(value),
            )
            .join(Part, Part.id == StockLevel.part_id)
            .outerjoin(PartCategory, PartCategory.id == Part.category_id)
            .where(*level_cond, StockLevel.on_hand > 0)
            .group_by(PartCategory.name)
            .order_by(func.sum(value).desc())
        )
    ]
    parts_in_stock = db.scalar(
        select(func.count(func.distinct(StockLevel.part_id))).where(
            *level_cond, StockLevel.on_hand > 0
        )
    )
    low = db.scalar(
        select(func.count(func.distinct(StockLevel.part_id))).where(
            *level_cond,
            StockLevel.min_quantity.is_not(None),
            StockLevel.on_hand - StockLevel.reserved <= StockLevel.min_quantity,
        )
    )

    mv_cond = [
        StockMovement.organisation_id == org,
        StockMovement.created_at >= start,
        StockMovement.created_at < end,
        *_in(StockMovement.branch_id, branches),
    ]
    movements = [
        MovementSummary(kind=kind, count=n, quantity=q, value=_money(v))
        for kind, n, q, v in db.execute(
            select(
                StockMovement.kind,
                func.count(),
                func.sum(StockMovement.quantity),
                func.sum(StockMovement.quantity * StockMovement.unit_cost),
            )
            .where(*mv_cond)
            .group_by(StockMovement.kind)
            .order_by(StockMovement.kind)
        )
    ]
    usage = [
        PartUsage(part=Ref(id=pid, name=name), sku=sku, quantity=-q, cost_value=_money(-v))
        for pid, name, sku, q, v in db.execute(
            select(
                Part.id,
                Part.name,
                Part.sku,
                func.sum(StockMovement.quantity),
                func.sum(StockMovement.quantity * StockMovement.unit_cost),
            )
            .join(Part, Part.id == StockMovement.part_id)
            .where(*mv_cond, StockMovement.kind.in_(("issue", "return")))
            .group_by(Part.id, Part.name, Part.sku)
            .having(func.sum(StockMovement.quantity) < 0)
            .order_by(func.sum(StockMovement.quantity * StockMovement.unit_cost))
            .limit(10)
        )
    ]

    po_cond = [PurchaseOrder.organisation_id == org, *_in(PurchaseOrder.branch_id, branches)]
    approved_n, approved_v = db.execute(
        select(func.count(), func.coalesce(func.sum(PurchaseOrder.total), 0)).where(
            *po_cond, PurchaseOrder.approved_at >= start, PurchaseOrder.approved_at < end
        )
    ).one()
    received_v = db.scalar(
        select(func.coalesce(func.sum(GoodsReceivedNote.total), 0)).where(
            GoodsReceivedNote.organisation_id == org,
            GoodsReceivedNote.received_at >= start,
            GoodsReceivedNote.received_at < end,
            *_in(GoodsReceivedNote.branch_id, branches),
        )
    )
    returned_v = db.scalar(
        select(func.coalesce(func.sum(SupplierReturn.total), 0))
        .join(PurchaseOrder, PurchaseOrder.id == SupplierReturn.purchase_order_id)
        .where(*po_cond, SupplierReturn.created_at >= start, SupplierReturn.created_at < end)
    )
    open_statuses = ("approved", "partially_received")
    today = utcnow().astimezone(tz).date()
    open_n, overdue_n = db.execute(
        select(
            func.count(),
            func.count().filter(PurchaseOrder.expected_date < today),
        ).where(*po_cond, PurchaseOrder.status.in_(open_statuses))
    ).one()
    open_v = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    (PurchaseOrderLine.quantity_ordered - PurchaseOrderLine.quantity_received)
                    * PurchaseOrderLine.unit_cost
                ),
                0,
            )
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(*po_cond, PurchaseOrder.status.in_(open_statuses))
    )

    params: dict[str, Any] = {
        "org": org,
        "all_branches": branches is None,
        "branches": list(branches or []),
    }
    checked, on_hand_bad, reserved_bad = db.execute(
        text(
            "SELECT count(*), "
            "count(*) FILTER (WHERE l.on_hand <> coalesce(m.q, 0)), "
            "count(*) FILTER (WHERE l.reserved <> coalesce(r.q, 0)) "
            "FROM stock_levels l "
            "LEFT JOIN (SELECT location_id, part_id, sum(quantity) q FROM stock_movements "
            "  WHERE organisation_id = :org GROUP BY 1, 2) m USING (location_id, part_id) "
            "LEFT JOIN (SELECT location_id, part_id, "
            "  sum(quantity - issued_quantity - released_quantity) q FROM stock_reservations "
            "  WHERE organisation_id = :org AND status = 'open' GROUP BY 1, 2) r "
            "  USING (location_id, part_id) "
            "WHERE l.organisation_id = :org "
            "AND (:all_branches OR l.branch_id = ANY(CAST(:branches AS uuid[])))"
        ),
        params,
    ).one()

    total_value = _money(sum((x.value for x in by_location), ZERO))
    return InventoryReport(
        period=Period(date_from=date_from, date_to=date_to, timezone=s.timezone),
        branch=branch,
        currency_code=s.currency_code,
        valuation=Valuation(
            as_at=today,
            total_value=total_value,
            parts_in_stock=parts_in_stock or 0,
            units=sum((x.units for x in by_location), ZERO),
            by_location=by_location,
            by_category=by_category,
        ),
        low_stock_parts=low or 0,
        movements=movements,
        usage=usage,
        purchasing=PurchasingSummary(
            orders_approved=approved_n,
            approved_value=_money(approved_v),
            received_value=_money(received_v),
            returned_value=_money(returned_v),
            open_orders=open_n,
            open_value=_money(open_v),
            overdue_orders=overdue_n,
        ),
        reconciliation=Reconciliation(
            stock_levels_checked=checked,
            on_hand_mismatches=on_hand_bad,
            reserved_mismatches=reserved_bad,
        ),
        definitions=INVENTORY_DEFINITIONS,
    )
