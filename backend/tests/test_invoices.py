"""Invoices, credit notes and payments: immutability, balances, idempotency, scoping."""

import threading
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models import AuditLog, Invoice, Payment, PaymentAllocation
from tests.conftest import Api, OrgFixture
from tests.test_quotations import ITEMS, _move, _quote, _send


@pytest.fixture
def vat(owner_api: Api) -> str:
    return owner_api.post(
        "/organisation/tax-rates",
        json={"name": "Standard", "rate_percent": "15", "is_default": True},
    ).json()["id"]


@pytest.fixture
def job(owner_api: Api, org: OrgFixture, vat: str) -> dict[str, Any]:
    """A job with an approved quotation (total 1742.25), at quality inspection."""
    c = owner_api.post(
        "/customers", json={"customer_type": "individual", "last_name": "Shikongo"}
    ).json()
    v = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 9 W",
            "make": "Toyota",
            "model": "Hilux",
        },
    ).json()
    j = owner_api.post(
        "/job-cards",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": c["id"],
            "vehicle_id": v["id"],
            "complaint": "Brakes",
        },
    ).json()
    _move(owner_api, j["id"], "diagnosis_in_progress")
    q = _send(owner_api, _quote(owner_api, j, vat))
    res = owner_api.post(
        f"/quotations/{q['quotation']['id']}/decisions",
        json={
            "decision": "approved",
            "method": "phone",
            "customer_name": "Ndapewa Shikongo",
            "evidence": "Phoned at 10:42",
        },
    )
    assert res.status_code == 201, res.text
    assert _move(owner_api, j["id"], "repair_in_progress").status_code == 200
    assert _move(owner_api, j["id"], "quality_inspection").status_code == 200
    return {**j, "customer_id": c["id"]}


def _draft(api: Api, job: dict[str, Any]) -> dict[str, Any]:
    res = api.post(f"/job-cards/{job['id']}/invoices")
    assert res.status_code == 201, res.text
    return res.json()


def _issued(api: Api, job: dict[str, Any]) -> dict[str, Any]:
    inv = _draft(api, job)
    res = api.post(f"/invoices/{inv['id']}/issue")
    assert res.status_code == 200, res.text
    return res.json()


def _pay(
    api: Api,
    org: OrgFixture,
    customer_id: str,
    amount: str,
    allocations: list[tuple[str, str]] = (),  # type: ignore[assignment]
    key: str | None = None,
    **extra: Any,
) -> Any:
    return api.post(
        "/payments",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={
            "branch_id": str(org.branch_id),
            "customer_id": customer_id,
            "method": "eft",
            "amount": amount,
            "allocations": [{"invoice_id": i, "amount": a} for i, a in allocations],
            **extra,
        },
    )


# --------------------------------------------------------------------------- drafts


def test_draft_prefilled_from_approved_quotation(owner_api: Api, job: dict[str, Any]) -> None:
    inv = _draft(owner_api, job)
    assert inv["status"] == "draft"
    assert inv["invoice_number"] is None
    assert inv["total"] == "1742.25"
    assert len(inv["items"]) == 3
    assert inv["quotation_version_id"]
    assert inv["payment_status"] == "draft"
    assert inv["capabilities"]["issue"] is True
    # One draft per job at a time.
    assert owner_api.post(f"/job-cards/{job['id']}/invoices").status_code == 409


def test_draft_edit_recalculates_and_can_be_deleted(
    owner_api: Api, job: dict[str, Any], vat: str
) -> None:
    inv = _draft(owner_api, job)
    res = owner_api.put(
        f"/invoices/{inv['id']}/draft",
        json={"items": ITEMS(vat)[:1], "notes": "Pads only"},
    )
    assert res.status_code == 200, res.text
    # 1.5 x 450 = 675 + 15% = 776.25
    assert (res.json()["subtotal"], res.json()["tax_total"], res.json()["total"]) == (
        "675.00",
        "101.25",
        "776.25",
    )
    assert owner_api.delete(f"/invoices/{inv['id']}").status_code == 204
    assert owner_api.get(f"/invoices/{inv['id']}").status_code == 404


def test_issue_requires_job_at_quality_inspection(
    owner_api: Api, org: OrgFixture, vat: str
) -> None:
    c = owner_api.post(
        "/customers", json={"customer_type": "individual", "last_name": "Nghipandulwa"}
    ).json()
    v = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 77 W",
            "make": "VW",
            "model": "Polo",
        },
    ).json()
    j = owner_api.post(
        "/job-cards",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": c["id"],
            "vehicle_id": v["id"],
            "complaint": "Noise",
        },
    ).json()
    inv = _draft(owner_api, j)
    owner_api.put(f"/invoices/{inv['id']}/draft", json={"items": ITEMS(vat)[:1]})
    res = owner_api.post(f"/invoices/{inv['id']}/issue")
    assert res.status_code == 409
    assert "quality inspection" in res.json()["error"]["message"]


def test_issue_numbers_and_locks_invoice(
    owner_api: Api, job: dict[str, Any], vat: str, db: Session
) -> None:
    inv = _issued(owner_api, job)
    assert inv["status"] == "issued"
    assert inv["invoice_number"] == "INV-000001"
    assert inv["issue_date"] == inv["due_date"]  # invoice_payment_days defaults to 0
    assert inv["payment_status"] == "unpaid"
    assert inv["balance_due"] == "1742.25"
    assert inv["capabilities"]["edit"] is False

    assert (
        owner_api.put(f"/invoices/{inv['id']}/draft", json={"items": ITEMS(vat)}).status_code == 409
    )
    assert owner_api.delete(f"/invoices/{inv['id']}").status_code == 409
    assert owner_api.post(f"/invoices/{inv['id']}/issue").status_code == 409
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "invoice.issued"))

    # The database refuses silent edits too.
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE invoices SET total = 1 WHERE id = :id"), {"id": inv["id"]})
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM invoice_items WHERE invoice_id = :id"), {"id": inv["id"]})
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM invoices WHERE id = :id"), {"id": inv["id"]})
    db.rollback()


def test_payment_terms_set_due_date(owner_api: Api, job: dict[str, Any]) -> None:
    assert (
        owner_api.patch("/organisation/settings", json={"invoice_payment_days": 30}).status_code
        == 200
    )
    inv = _issued(owner_api, job)
    assert (date.fromisoformat(inv["due_date"]) - date.fromisoformat(inv["issue_date"])).days == 30


# --------------------------------------------------------------------------- payments


def test_partial_and_full_payment_balances(
    owner_api: Api, job: dict[str, Any], org: OrgFixture
) -> None:
    inv = _issued(owner_api, job)
    res = _pay(owner_api, org, job["customer_id"], "500.00", [(inv["id"], "500.00")])
    assert res.status_code == 201, res.text
    first = res.json()
    assert first["receipt_number"] == "RCT-000001"
    assert first["unallocated"] == "0.00"

    after = owner_api.get(f"/invoices/{inv['id']}").json()
    assert (after["amount_paid"], after["balance_due"], after["payment_status"]) == (
        "500.00",
        "1242.25",
        "partially_paid",
    )
    # Cannot allocate more than the balance due.
    over = _pay(owner_api, org, job["customer_id"], "2000.00", [(inv["id"], "2000.00")])
    assert over.status_code == 409
    # Pay the rest and leave 57.75 as credit.
    rest = _pay(owner_api, org, job["customer_id"], "1300.00", [(inv["id"], "1242.25")])
    assert rest.status_code == 201
    assert rest.json()["unallocated"] == "57.75"
    final = owner_api.get(f"/invoices/{inv['id']}").json()
    assert (final["balance_due"], final["payment_status"]) == ("0.00", "paid")
    bal = owner_api.get(f"/customers/{job['customer_id']}/balance").json()
    assert (bal["outstanding"], bal["unallocated_credit"]) == ("0.00", "57.75")
    assert (
        owner_api.get("/payments", params={"customer_id": job["customer_id"]}).json()["total"] == 2
    )


def test_allocations_cannot_exceed_payment_or_go_to_drafts(
    owner_api: Api, job: dict[str, Any], org: OrgFixture
) -> None:
    draft = _draft(owner_api, job)
    assert (
        _pay(owner_api, org, job["customer_id"], "10.00", [(draft["id"], "10.00")]).status_code
        == 409
    )
    owner_api.post(f"/invoices/{draft['id']}/issue")
    res = _pay(
        owner_api,
        org,
        job["customer_id"],
        "100.00",
        [(draft["id"], "60.00"), (draft["id"], "60.00")],
    )
    assert res.status_code == 409


def test_deposit_allocated_later(owner_api: Api, job: dict[str, Any], org: OrgFixture) -> None:
    deposit = _pay(owner_api, org, job["customer_id"], "1000.00").json()
    assert deposit["unallocated"] == "1000.00"
    inv = _issued(owner_api, job)
    res = owner_api.post(
        f"/payments/{deposit['id']}/allocations",
        json={"allocations": [{"invoice_id": inv["id"], "amount": "1000.00"}]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["unallocated"] == "0.00"
    again = owner_api.post(
        f"/payments/{deposit['id']}/allocations",
        json={"allocations": [{"invoice_id": inv["id"], "amount": "1.00"}]},
    )
    assert again.status_code == 409
    assert owner_api.get(f"/invoices/{inv['id']}").json()["balance_due"] == "742.25"


def test_duplicate_payment_submission_is_idempotent(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, db: Session
) -> None:
    inv = _issued(owner_api, job)
    key = "pay-" + uuid.uuid4().hex
    first = _pay(owner_api, org, job["customer_id"], "100.00", [(inv["id"], "100.00")], key=key)
    second = _pay(owner_api, org, job["customer_id"], "100.00", [(inv["id"], "100.00")], key=key)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert owner_api.get(f"/invoices/{inv['id']}").json()["amount_paid"] == "100.00"

    different = _pay(owner_api, org, job["customer_id"], "200.00", key=key)
    assert different.status_code == 409
    assert different.json()["error"]["code"] == "idempotency_key_reused"

    missing = owner_api.post(
        "/payments",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": job["customer_id"],
            "method": "cash",
            "amount": "1.00",
        },
    )
    assert missing.status_code == 422
    assert db.scalar(select(Payment.id).where(Payment.amount == Decimal("1.00"))) is None


def test_concurrent_payments_cannot_over_allocate(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, new_api: Any
) -> None:
    inv = _issued(owner_api, job)
    apis = [new_api() for _ in range(4)]
    for a in apis:
        a.login(org.owner_email)
    results: list[int] = []

    def pay(a: Api) -> None:
        results.append(
            _pay(a, org, job["customer_id"], "1000.00", [(inv["id"], "1000.00")]).status_code
        )

    threads = [threading.Thread(target=pay, args=(a,)) for a in apis]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 409, 409, 409]
    with get_sessionmaker()() as s:
        paid = s.scalar(select(Invoice.amount_paid).where(Invoice.id == uuid.UUID(inv["id"])))
        allocated = s.scalars(
            select(PaymentAllocation.amount).where(
                PaymentAllocation.invoice_id == uuid.UUID(inv["id"])
            )
        ).all()
    assert paid == Decimal("1000.00") == sum(allocated)


def test_payments_are_append_only(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, db: Session
) -> None:
    p = _pay(owner_api, org, job["customer_id"], "50.00").json()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE payments SET amount = 5 WHERE id = :id"), {"id": p["id"]})
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM payments WHERE id = :id"), {"id": p["id"]})
    db.rollback()


def test_reversal_undoes_allocations_once(
    owner_api: Api, job: dict[str, Any], org: OrgFixture
) -> None:
    inv = _issued(owner_api, job)
    p = _pay(owner_api, org, job["customer_id"], "600.00", [(inv["id"], "500.00")]).json()
    no_reason = owner_api.post(
        f"/payments/{p['id']}/reverse", headers={"Idempotency-Key": uuid.uuid4().hex}, json={}
    )
    assert no_reason.status_code == 422
    res = owner_api.post(
        f"/payments/{p['id']}/reverse",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={"reason": "EFT bounced"},
    )
    assert res.status_code == 201, res.text
    rev = res.json()
    assert rev["kind"] == "reversal"
    assert rev["reverses_receipt"] == p["receipt_number"]
    assert rev["allocations"][0]["amount"] == "-500.00"
    assert owner_api.get(f"/invoices/{inv['id']}").json()["balance_due"] == "1742.25"
    original = owner_api.get(f"/payments/{p['id']}").json()
    assert original["reversed_by_receipt"] == rev["receipt_number"]
    assert original["unallocated"] == "0.00"
    twice = owner_api.post(
        f"/payments/{p['id']}/reverse",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={"reason": "Again"},
    )
    assert twice.status_code == 409
    # Reversed payments cannot be allocated.
    assert (
        owner_api.post(
            f"/payments/{p['id']}/allocations",
            json={"allocations": [{"invoice_id": inv["id"], "amount": "10.00"}]},
        ).status_code
        == 409
    )
    # The list (batched read models) shows exactly what the detail view shows.
    _pay(owner_api, org, job["customer_id"], "300.00", [(inv["id"], "200.00")])
    listed = owner_api.get("/payments").json()["items"]
    assert len(listed) == 3
    for item in listed:
        assert item == owner_api.get(f"/payments/{item['id']}").json()
    assert {i["unallocated"] for i in listed} == {"0.00", "100.00"}


# --------------------------------------------------------------------------- credit notes


def test_credit_note_and_refund_of_overpayment(
    owner_api: Api, job: dict[str, Any], org: OrgFixture
) -> None:
    inv = _issued(owner_api, job)
    _pay(owner_api, org, job["customer_id"], "1742.25", [(inv["id"], "1742.25")])
    res = owner_api.post(
        f"/invoices/{inv['id']}/credit-notes",
        json={
            "reason": "Goodwill: labour overcharged",
            "lines": [{"description": "Labour adjustment", "quantity": "1", "unit_price": "100"}],
        },
    )
    assert res.status_code == 201, res.text
    credited = res.json()
    assert credited["credit_notes"][0]["credit_note_number"] == "CN-000001"
    assert credited["amount_credited"] == "100.00"
    assert (credited["balance_due"], credited["payment_status"]) == ("-100.00", "overpaid")
    assert credited["capabilities"]["refund"] is True
    # The invoice itself did not change.
    assert credited["total"] == "1742.25"

    too_much = owner_api.post(
        "/refunds",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={"invoice_id": inv["id"], "method": "eft", "amount": "150.00", "reason": "Refund"},
    )
    assert too_much.status_code == 409
    ok = owner_api.post(
        "/refunds",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={"invoice_id": inv["id"], "method": "eft", "amount": "100.00", "reason": "Refund"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["kind"] == "refund"
    final = owner_api.get(f"/invoices/{inv['id']}").json()
    assert (final["amount_paid"], final["balance_due"], final["payment_status"]) == (
        "1642.25",
        "0.00",
        "paid",
    )


def test_full_credit_and_limits(owner_api: Api, job: dict[str, Any]) -> None:
    inv = _issued(owner_api, job)
    over = owner_api.post(
        f"/invoices/{inv['id']}/credit-notes",
        json={
            "reason": "Too much",
            "lines": [{"description": "x", "quantity": "1", "unit_price": "5000"}],
        },
    )
    assert over.status_code == 409
    full = owner_api.post(
        f"/invoices/{inv['id']}/credit-notes", json={"reason": "Invoiced in error", "full": True}
    )
    assert full.status_code == 201, full.text
    body = full.json()
    assert (body["amount_credited"], body["balance_due"], body["payment_status"]) == (
        "1742.25",
        "0.00",
        "credited",
    )
    assert body["capabilities"]["credit"] is False
    # A new draft can now be started for the job.
    assert owner_api.post(f"/job-cards/{job['id']}/invoices").status_code == 201


def test_drafts_cannot_be_credited(owner_api: Api, job: dict[str, Any]) -> None:
    inv = _draft(owner_api, job)
    assert (
        owner_api.post(
            f"/invoices/{inv['id']}/credit-notes", json={"reason": "Not issued", "full": True}
        ).status_code
        == 409
    )


# --------------------------------------------------------------------------- access


def test_cross_organisation_invoices_invisible(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, make_org: Any, new_api: Any
) -> None:
    inv = _issued(owner_api, job)
    p = _pay(owner_api, org, job["customer_id"], "10.00").json()
    other: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(other.owner_email)
    assert b.get(f"/invoices/{inv['id']}").status_code == 404
    assert (
        b.post(
            f"/invoices/{inv['id']}/credit-notes", json={"reason": "x" * 5, "full": True}
        ).status_code
        == 404
    )
    assert b.get(f"/payments/{p['id']}").status_code == 404
    assert b.get(f"/customers/{job['customer_id']}/balance").status_code == 404
    assert b.get("/invoices").json()["total"] == 0
    assert b.get("/payments").json()["total"] == 0
    # Paying another organisation's invoice from your own customer is refused.
    bc = b.post("/customers", json={"customer_type": "individual", "last_name": "B"}).json()
    res = _pay(b, other, bc["id"], "10.00", [(inv["id"], "10.00")])
    assert res.status_code == 404
    # Recording a payment for another organisation's customer is refused.
    assert _pay(b, other, job["customer_id"], "10.00").status_code == 404


def test_role_permissions(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, new_api: Any
) -> None:
    inv = _issued(owner_api, job)
    p = _pay(owner_api, org, job["customer_id"], "10.00").json()

    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert mech.get(f"/invoices/{inv['id']}").status_code == 404
    assert mech.get("/invoices").status_code == 403
    assert _pay(mech, org, job["customer_id"], "10.00").status_code == 403

    org.add_user("advisor@example.com", [(org.role("service_advisor"), org.branch_id)])
    advisor: Api = new_api()
    advisor.login("advisor@example.com")
    assert advisor.get(f"/invoices/{inv['id']}").status_code == 200
    assert _pay(advisor, org, job["customer_id"], "10.00").status_code == 201
    # Advisors cannot credit, refund or reverse.
    assert (
        advisor.post(
            f"/invoices/{inv['id']}/credit-notes", json={"reason": "Nope", "full": True}
        ).status_code
        == 403
    )
    assert (
        advisor.post(
            f"/payments/{p['id']}/reverse",
            headers={"Idempotency-Key": uuid.uuid4().hex},
            json={"reason": "Mistake"},
        ).status_code
        == 403
    )

    # Branch scope: an accounts user in another branch cannot see this branch's invoices.
    other_branch = org.add_branch("WHK2")
    org.add_user("acc@example.com", [(org.role("accounts"), other_branch.id)])
    acc: Api = new_api()
    acc.login("acc@example.com")
    assert acc.get(f"/invoices/{inv['id']}").status_code == 404
    assert acc.get("/invoices").json()["total"] == 0
    assert _pay(acc, org, job["customer_id"], "10.00").status_code == 403
