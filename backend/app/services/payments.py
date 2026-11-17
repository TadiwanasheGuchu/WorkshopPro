"""Payments, allocations, refunds and reversals (CLAUDE.md §3.9).

Rules:
- Payments are records of money received; nothing here processes cards.
- Every payment needs an Idempotency-Key. Retrying with the same key and the same body
  returns the original payment; the same key with a different body is rejected.
- Payments are never edited or deleted (database trigger). Mistakes are reversed with a
  linked reversal; overpayments are paid back with a refund against the invoice.
- Allocations change invoice balances in the same transaction, with the invoice rows
  locked in a fixed order so concurrent payments cannot over-allocate.
- Money received but not allocated stays on the payment as customer credit and can be
  allocated to an invoice later.
"""

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import Branch, Customer, Invoice, Payment, PaymentAllocation, User
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.invoice import (
    AllocateRequest,
    AllocationInput,
    AllocationRead,
    CustomerBalance,
    PaymentCreate,
    PaymentRead,
    RefundCreate,
    ReverseRequest,
)
from app.schemas.job_card import Ref
from app.services import audit, numbering
from app.services.idempotency import check_replay, fingerprint
from app.services.invoices import ZERO, balance_due, org_settings, today, visible_branches
from app.services.invoices import _list_item as invoice_list_item


def _by_key(db: Session, organisation_id: uuid.UUID, key: str) -> Payment | None:
    return db.scalar(
        select(Payment).where(
            Payment.organisation_id == organisation_id, Payment.idempotency_key == key
        )
    )


def _replay(existing: Payment, print_: str) -> Payment:
    check_replay(existing.request_fingerprint, print_)
    return existing


# --------------------------------------------------------------------------- reads


def allocated_total(db: Session, payment_id: uuid.UUID) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.payment_id == payment_id
        )
    ) or Decimal(0)


def _unallocated(db: Session, p: Payment) -> Decimal:
    """Customer credit still available on this payment."""
    if p.kind != "payment":
        return ZERO
    if db.scalar(select(Payment.id).where(Payment.reverses_payment_id == p.id)):
        return ZERO
    return p.amount - allocated_total(db, p.id)


def read(db: Session, p: Payment) -> PaymentRead:
    return read_many(db, [p])[0]


def read_many(db: Session, payments: list[Payment]) -> list[PaymentRead]:
    """Read models for several payments with a fixed number of queries (list pages)."""
    if not payments:
        return []
    ids = [p.id for p in payments]
    allocations: dict[uuid.UUID, list[AllocationRead]] = defaultdict(list)
    allocated: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for pid, inv_id, number, amount in db.execute(
        select(
            PaymentAllocation.payment_id,
            PaymentAllocation.invoice_id,
            Invoice.invoice_number,
            PaymentAllocation.amount,
        )
        .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
        .where(PaymentAllocation.payment_id.in_(ids))
        .order_by(PaymentAllocation.created_at)
    ):
        allocations[pid].append(
            AllocationRead(invoice_id=inv_id, invoice_number=number, amount=amount)
        )
        allocated[pid] += amount
    reversed_by = dict(
        db.execute(
            select(Payment.reverses_payment_id, Payment.receipt_number).where(
                Payment.reverses_payment_id.in_(ids)
            )
        ).all()
    )
    targets = {p.reverses_payment_id for p in payments if p.reverses_payment_id}
    receipts = (
        dict(
            db.execute(
                select(Payment.id, Payment.receipt_number).where(Payment.id.in_(targets))
            ).all()
        )
        if targets
        else {}
    )
    branches = dict(
        db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_({p.branch_id for p in payments}))
        ).all()
    )
    customers = dict(
        db.execute(
            select(Customer.id, Customer.display_name).where(
                Customer.id.in_({p.customer_id for p in payments})
            )
        ).all()
    )
    users = dict(
        db.execute(
            select(User.id, User.full_name).where(
                User.id.in_({p.recorded_by_user_id for p in payments})
            )
        ).all()
    )

    def unallocated(p: Payment) -> Decimal:
        # Customer credit still available on this payment.
        if p.kind != "payment" or p.id in reversed_by:
            return ZERO
        return p.amount - allocated[p.id]

    return [
        PaymentRead(
            id=p.id,
            receipt_number=p.receipt_number,
            kind=p.kind,  # type: ignore[arg-type]
            method=p.method,  # type: ignore[arg-type]
            amount=p.amount,
            currency_code=p.currency_code,
            received_at=p.received_at,
            reference=p.reference,
            notes=p.notes,
            branch=Ref(id=p.branch_id, name=branches.get(p.branch_id)),
            customer=Ref(id=p.customer_id, name=customers.get(p.customer_id)),
            recorded_by=users.get(p.recorded_by_user_id) or "",
            allocations=allocations[p.id],
            unallocated=unallocated(p),
            reversed_by_receipt=reversed_by.get(p.id),
            reverses_receipt=receipts.get(p.reverses_payment_id) if p.reverses_payment_id else None,
        )
        for p in payments
    ]


def _load(
    db: Session, principal: Principal, payment_id: uuid.UUID, *, lock: bool = False
) -> Payment:
    stmt = select(Payment).where(
        Payment.id == payment_id, Payment.organisation_id == principal.organisation_id
    )
    if lock:
        stmt = stmt.with_for_update()
    p = db.scalar(stmt)
    if p is None or not principal.can(P.INVOICES_VIEW, p.branch_id):
        raise NotFoundError("Payment not found.")
    return p


def get_payment(db: Session, principal: Principal, payment_id: uuid.UUID) -> PaymentRead:
    return read(db, _load(db, principal, payment_id))


def list_payments(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    customer_id: uuid.UUID | None = None,
    kind: str | None = None,
    search: str | None = None,
) -> tuple[list[PaymentRead], int]:
    branches = visible_branches(principal)
    conditions: list[Any] = [Payment.organisation_id == principal.organisation_id]
    if branches is not None:
        conditions.append(Payment.branch_id.in_(branches))
    if customer_id:
        conditions.append(Payment.customer_id == customer_id)
    if kind:
        conditions.append(Payment.kind == kind)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(
            Payment.receipt_number.ilike(term)
            | Payment.reference.ilike(term)
            | Payment.customer_id.in_(select(Customer.id).where(Customer.display_name.ilike(term)))
        )
    total = db.scalar(select(func.count()).select_from(Payment).where(*conditions)) or 0
    rows = db.scalars(
        select(Payment)
        .where(*conditions)
        .order_by(Payment.received_at.desc(), Payment.created_at.desc())
        .limit(params.page_size)
        .offset(params.offset)
    )
    return read_many(db, list(rows)), total


def customer_balance(db: Session, principal: Principal, customer_id: uuid.UUID) -> CustomerBalance:
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.organisation_id == principal.organisation_id
        )
    )
    if customer is None:
        raise NotFoundError("Customer not found.")
    branches = visible_branches(principal)
    on = today(db, principal.organisation_id)
    inv_conditions: list[Any] = [Invoice.customer_id == customer.id, Invoice.status == "issued"]
    pay_conditions: list[Any] = [Payment.customer_id == customer.id, Payment.kind == "payment"]
    if branches is not None:
        inv_conditions.append(Invoice.branch_id.in_(branches))
        pay_conditions.append(Payment.branch_id.in_(branches))
    invoices = list(db.scalars(select(Invoice).where(*inv_conditions).order_by(Invoice.due_date)))
    open_invoices = [i for i in invoices if balance_due(i) > 0]
    credit = sum(
        (_unallocated(db, p) for p in db.scalars(select(Payment).where(*pay_conditions))), ZERO
    )
    overpaid = sum((-balance_due(i) for i in invoices if balance_due(i) < 0), ZERO)
    currency = org_settings(db, principal.organisation_id).currency_code
    return CustomerBalance(
        customer_id=customer.id,
        currency_code=currency,
        outstanding=sum((balance_due(i) for i in open_invoices), ZERO),
        unallocated_credit=credit + overpaid,
        open_invoices=[
            invoice_list_item(i, customer.display_name, None, on) for i in open_invoices
        ],
    )


# --------------------------------------------------------------------------- writes


def _lock_invoices(
    db: Session, principal: Principal, customer_id: uuid.UUID, ids: list[uuid.UUID]
) -> dict[uuid.UUID, Invoice]:
    """Lock the invoices in id order (deadlock-free) and check they can take money."""
    rows = {
        i.id: i
        for i in db.scalars(
            select(Invoice)
            .where(Invoice.id.in_(ids), Invoice.organisation_id == principal.organisation_id)
            .order_by(Invoice.id)
            .with_for_update()
        )
    }
    for invoice_id in ids:
        inv = rows.get(invoice_id)
        if inv is None or not principal.can(P.INVOICES_VIEW, inv.branch_id):
            raise NotFoundError("Invoice not found.", details={"invoice_id": str(invoice_id)})
        if inv.customer_id != customer_id:
            raise ConflictError(
                "The invoice belongs to a different customer.",
                details={"invoice_id": str(invoice_id)},
            )
        if inv.status != "issued":
            raise ConflictError(
                "Only issued invoices can be paid.", details={"invoice_id": str(invoice_id)}
            )
    return rows


def _allocate(
    db: Session,
    principal: Principal,
    payment: Payment,
    allocations: list[AllocationInput],
    available: Decimal,
) -> None:
    merged: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for a in allocations:
        merged[a.invoice_id] += a.amount
    if sum(merged.values(), ZERO) > available:
        raise ConflictError(
            "Allocations add up to more than the payment.",
            details={"available": str(available)},
        )
    invoices = _lock_invoices(db, principal, payment.customer_id, list(merged))
    for invoice_id, amount in merged.items():
        inv = invoices[invoice_id]
        if inv.currency_code != payment.currency_code:
            raise ConflictError("The invoice is in a different currency.")
        due = balance_due(inv)
        if amount > due:
            raise ConflictError(
                f"{inv.invoice_number}: the amount is more than the balance due.",
                details={"invoice_id": str(invoice_id), "balance_due": str(due)},
            )
        db.add(
            PaymentAllocation(
                organisation_id=payment.organisation_id,
                payment_id=payment.id,
                invoice_id=inv.id,
                amount=amount,
                created_by_user_id=principal.user_id,
            )
        )
        inv.amount_paid += amount


def record_payment(
    db: Session, principal: Principal, body: PaymentCreate, idempotency_key: str
) -> tuple[PaymentRead, bool]:
    """Returns (payment, created). created is False when an earlier identical request with
    the same key is replayed."""
    print_ = fingerprint({"op": "payment", **body.model_dump(mode="json")})
    existing = _by_key(db, principal.organisation_id, idempotency_key)
    if existing:
        return read(db, _replay(existing, print_)), False

    principal.require(P.PAYMENTS_RECORD, body.branch_id)
    if not db.scalar(
        select(Branch.id).where(
            Branch.id == body.branch_id, Branch.organisation_id == principal.organisation_id
        )
    ):
        raise NotFoundError("Branch not found.")
    if not db.scalar(
        select(Customer.id).where(
            Customer.id == body.customer_id, Customer.organisation_id == principal.organisation_id
        )
    ):
        raise NotFoundError("Customer not found.")
    s = org_settings(db, principal.organisation_id)
    received_at = body.received_at or utcnow()
    if received_at > utcnow():
        raise ConflictError("A payment cannot be dated in the future.")
    payment = Payment(
        organisation_id=principal.organisation_id,
        branch_id=body.branch_id,
        customer_id=body.customer_id,
        kind="payment",
        receipt_number=numbering.allocate(
            db, principal.organisation_id, numbering.DocumentType.RECEIPT
        ),
        method=body.method,
        amount=body.amount,
        currency_code=s.currency_code,
        received_at=received_at,
        reference=body.reference,
        notes=body.notes,
        idempotency_key=idempotency_key,
        request_fingerprint=print_,
        recorded_by_user_id=principal.user_id,
    )
    db.add(payment)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent request with the same key won the race.
        db.rollback()
        existing = _by_key(db, principal.organisation_id, idempotency_key)
        if existing is None:  # pragma: no cover - some other constraint failed
            raise
        return read(db, _replay(existing, print_)), False

    if body.allocations:
        _allocate(db, principal, payment, body.allocations, payment.amount)
    audit.record(
        db,
        organisation_id=payment.organisation_id,
        branch_id=payment.branch_id,
        actor=principal,
        action="payment.recorded",
        entity_type="payment",
        entity_id=payment.id,
        summary=f"Payment {payment.receipt_number} of {payment.currency_code} "
        f"{payment.amount} ({payment.method}) recorded",
        changes={"allocations": [None, [a.model_dump() for a in body.allocations]]},
    )
    db.commit()
    return read(db, payment), True


def allocate_credit(
    db: Session, principal: Principal, payment_id: uuid.UUID, body: AllocateRequest
) -> PaymentRead:
    payment = _load(db, principal, payment_id, lock=True)
    principal.require(P.PAYMENTS_RECORD, payment.branch_id)
    if payment.kind != "payment":
        raise ConflictError("Only payments received can be allocated.")
    available = _unallocated(db, payment)
    if available <= 0:
        raise ConflictError("Nothing is left to allocate on this payment.")
    _allocate(db, principal, payment, body.allocations, available)
    audit.record(
        db,
        organisation_id=payment.organisation_id,
        branch_id=payment.branch_id,
        actor=principal,
        action="payment.allocated",
        entity_type="payment",
        entity_id=payment.id,
        summary=f"Credit on {payment.receipt_number} allocated to invoices",
        changes={"allocations": [None, [a.model_dump() for a in body.allocations]]},
    )
    db.commit()
    return read(db, payment)


def reverse(
    db: Session,
    principal: Principal,
    payment_id: uuid.UUID,
    body: ReverseRequest,
    idempotency_key: str,
) -> tuple[PaymentRead, bool]:
    """Undo a payment recorded in error (wrong customer, bounced EFT). Every allocation is
    undone, and the reversal is linked to the original."""
    print_ = fingerprint({"op": "reversal", "payment_id": str(payment_id), **body.model_dump()})
    existing = _by_key(db, principal.organisation_id, idempotency_key)
    if existing:
        return read(db, _replay(existing, print_)), False

    original = _load(db, principal, payment_id, lock=True)
    principal.require(P.PAYMENTS_REFUND, original.branch_id)
    existing = _by_key(db, principal.organisation_id, idempotency_key)
    if existing:  # a concurrent retry finished while we waited for the lock
        return read(db, _replay(existing, print_)), False
    if original.kind != "payment":
        raise ConflictError("Only payments received can be reversed.")
    if db.scalar(select(Payment.id).where(Payment.reverses_payment_id == original.id)):
        raise ConflictError("This payment was already reversed.")

    per_invoice: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for invoice_id, amount in db.execute(
        select(PaymentAllocation.invoice_id, PaymentAllocation.amount).where(
            PaymentAllocation.payment_id == original.id
        )
    ):
        per_invoice[invoice_id] += amount
    invoices = {
        i.id: i
        for i in db.scalars(
            select(Invoice)
            .where(Invoice.id.in_(list(per_invoice)))
            .order_by(Invoice.id)
            .with_for_update()
        )
    }
    reversal = Payment(
        organisation_id=original.organisation_id,
        branch_id=original.branch_id,
        customer_id=original.customer_id,
        kind="reversal",
        receipt_number=numbering.allocate(
            db, original.organisation_id, numbering.DocumentType.RECEIPT
        ),
        method=original.method,
        amount=original.amount,
        currency_code=original.currency_code,
        received_at=utcnow(),
        reference=original.receipt_number,
        notes=body.reason,
        reverses_payment_id=original.id,
        idempotency_key=idempotency_key,
        request_fingerprint=print_,
        recorded_by_user_id=principal.user_id,
    )
    db.add(reversal)
    db.flush()
    for invoice_id, amount in per_invoice.items():
        if amount == 0:
            continue
        inv = invoices[invoice_id]
        if inv.amount_paid < amount:
            raise ConflictError(
                f"{inv.invoice_number}: a refund was paid after this payment. "
                "Reverse the refund's effect with a new payment first.",
            )
        db.add(
            PaymentAllocation(
                organisation_id=original.organisation_id,
                payment_id=reversal.id,
                invoice_id=invoice_id,
                amount=-amount,
                created_by_user_id=principal.user_id,
            )
        )
        inv.amount_paid -= amount
    audit.record(
        db,
        organisation_id=original.organisation_id,
        branch_id=original.branch_id,
        actor=principal,
        action="payment.reversed",
        entity_type="payment",
        entity_id=original.id,
        summary=f"Payment {original.receipt_number} reversed by {reversal.receipt_number}: "
        f"{body.reason}",
    )
    db.commit()
    return read(db, reversal), True


def refund(
    db: Session, principal: Principal, body: RefundCreate, idempotency_key: str
) -> tuple[PaymentRead, bool]:
    """Pay back money the customer overpaid on an invoice (usually after a credit note)."""
    print_ = fingerprint({"op": "refund", **body.model_dump(mode="json")})
    existing = _by_key(db, principal.organisation_id, idempotency_key)
    if existing:
        return read(db, _replay(existing, print_)), False

    inv = db.scalar(
        select(Invoice)
        .where(Invoice.id == body.invoice_id, Invoice.organisation_id == principal.organisation_id)
        .with_for_update()
    )
    if inv is None or not principal.can(P.INVOICES_VIEW, inv.branch_id):
        raise NotFoundError("Invoice not found.")
    principal.require(P.PAYMENTS_REFUND, inv.branch_id)
    existing = _by_key(db, principal.organisation_id, idempotency_key)
    if existing:  # a concurrent retry finished while we waited for the lock
        return read(db, _replay(existing, print_)), False
    overpaid = -balance_due(inv)
    if overpaid <= 0:
        raise ConflictError("Nothing has been overpaid on this invoice.")
    if body.amount > overpaid:
        raise ConflictError(
            "A refund cannot exceed the overpaid amount.", details={"overpaid": str(overpaid)}
        )
    payment = Payment(
        organisation_id=inv.organisation_id,
        branch_id=inv.branch_id,
        customer_id=inv.customer_id,
        kind="refund",
        receipt_number=numbering.allocate(db, inv.organisation_id, numbering.DocumentType.RECEIPT),
        method=body.method,
        amount=body.amount,
        currency_code=inv.currency_code,
        received_at=utcnow(),
        reference=body.reference,
        notes=body.reason,
        idempotency_key=idempotency_key,
        request_fingerprint=print_,
        recorded_by_user_id=principal.user_id,
    )
    db.add(payment)
    db.flush()
    db.add(
        PaymentAllocation(
            organisation_id=inv.organisation_id,
            payment_id=payment.id,
            invoice_id=inv.id,
            amount=-body.amount,
            created_by_user_id=principal.user_id,
        )
    )
    inv.amount_paid -= body.amount
    audit.record(
        db,
        organisation_id=inv.organisation_id,
        branch_id=inv.branch_id,
        actor=principal,
        action="payment.refunded",
        entity_type="invoice",
        entity_id=inv.id,
        summary=f"Refund {payment.receipt_number} of {inv.currency_code} {body.amount} "
        f"on {inv.invoice_number}: {body.reason}",
    )
    db.commit()
    return read(db, payment), True
