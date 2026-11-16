import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.integrations.email import InMemoryEmailSender
from app.models import AuditLog, QuotationDecision, QuotationLink, QuotationVersion
from tests.conftest import Api, OrgFixture


@pytest.fixture
def job(org: OrgFixture, owner_api: Api) -> dict[str, Any]:
    c = owner_api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "last_name": "Shikongo",
            "contacts": [{"kind": "email", "value": "ndapewa@example.com"}],
        },
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
    return owner_api.post(
        f"/job-cards/{j['id']}/transitions",
        json={"to_status": "diagnosis_in_progress", "version": 1},
    ).json()


@pytest.fixture
def vat(owner_api: Api) -> str:
    return owner_api.post(
        "/organisation/tax-rates",
        json={"name": "Standard", "rate_percent": "15", "is_default": True},
    ).json()["id"]


ITEMS = lambda vat: [  # noqa: E731
    {
        "kind": "labour",
        "description": "Replace front pads",
        "quantity": "1.5",
        "unit_price": "450.00",
        "tax_rate_id": vat,
    },
    {
        "kind": "part",
        "description": "Brake pad set",
        "part_number": "BP-1234",
        "quantity": "1",
        "unit_price": "890.00",
        "tax_rate_id": vat,
    },
    {
        "kind": "discount",
        "description": "Loyalty discount",
        "quantity": "1",
        "unit_price": "50.00",
        "tax_rate_id": vat,
    },
]


def _quote(api: Api, job: dict[str, Any], vat: str) -> dict[str, Any]:
    q = api.post(f"/job-cards/{job['id']}/quotation").json()
    res = api.put(
        f"/quotations/{q['id']}/draft",
        json={"items": ITEMS(vat), "terms": "Payment on collection."},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _send(api: Api, q: dict[str, Any]) -> dict[str, Any]:
    res = api.post(f"/quotations/{q['id']}/send", json={"email_customer": True})
    assert res.status_code == 200, res.text
    return res.json()


def _token(url: str) -> str:
    return url.split("#token=")[1]


def _move(api: Api, job_id: str, to: str) -> Any:
    j = api.get(f"/job-cards/{job_id}").json()
    return api.post(
        f"/job-cards/{job_id}/transitions", json={"to_status": to, "version": j["version"]}
    )


# --------------------------------------------------------------------------- drafting


def test_draft_totals_and_tax(owner_api: Api, job: dict[str, Any], vat: str) -> None:
    q = _quote(owner_api, job, vat)
    v = q["current"]
    assert q["quote_number"] == "QT-000001"
    assert v["status"] == "draft"
    # labour 675.00, part 890.00, discount -50.00 => 1515.00 ex tax; tax 227.25; total 1742.25
    assert (v["subtotal"], v["tax_total"], v["total"]) == ("1515.00", "227.25", "1742.25")
    assert [i["line_total"] for i in v["items"]] == ["776.25", "1023.50", "-57.50"]
    assert v["items"][0]["tax_rate_name"] == "Standard"
    assert owner_api.post(f"/job-cards/{job['id']}/quotation").status_code == 409  # one per job


def test_prices_including_tax(owner_api: Api, job: dict[str, Any], vat: str) -> None:
    owner_api.patch("/organisation/settings", json={"prices_include_tax": True})
    q = owner_api.post(f"/job-cards/{job['id']}/quotation").json()
    v = owner_api.put(
        f"/quotations/{q['id']}/draft",
        json={
            "items": [
                {
                    "kind": "part",
                    "description": "Battery",
                    "quantity": "1",
                    "unit_price": "1150.00",
                    "tax_rate_id": vat,
                }
            ]
        },
    ).json()["current"]
    assert v["prices_include_tax"] is True
    assert (v["subtotal"], v["tax_total"], v["total"]) == ("1000.00", "150.00", "1150.00")


def test_invalid_lines_rejected(
    owner_api: Api, job: dict[str, Any], vat: str, make_org: Any, new_api: Any
) -> None:
    q = owner_api.post(f"/job-cards/{job['id']}/quotation").json()
    bad = [
        {"kind": "part", "description": "X", "quantity": "0", "unit_price": "1"},
        {"kind": "part", "description": "X", "quantity": "1", "unit_price": "-5"},
        {"kind": "part", "description": "X", "quantity": "1", "unit_price": "1.005"},
        {"kind": "gift", "description": "X", "quantity": "1", "unit_price": "1"},
    ]
    for item in bad:
        assert (
            owner_api.put(f"/quotations/{q['id']}/draft", json={"items": [item]}).status_code == 422
        ), item
    other: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(other.owner_email)
    foreign_rate = b.post(
        "/organisation/tax-rates", json={"name": "Theirs", "rate_percent": "10"}
    ).json()["id"]
    res = owner_api.put(
        f"/quotations/{q['id']}/draft",
        json={
            "items": [
                {
                    "kind": "part",
                    "description": "X",
                    "quantity": "1",
                    "unit_price": "1",
                    "tax_rate_id": foreign_rate,
                }
            ]
        },
    )
    assert res.status_code == 409


# ---------------------------------------------------------------- sending and customer link


def test_send_locks_version_and_emails_link(
    owner_api: Api, job: dict[str, Any], vat: str, outbox: InMemoryEmailSender
) -> None:
    q = _quote(owner_api, job, vat)
    sent = _send(owner_api, q)
    assert sent["emailed_to"] == "ndapewa@example.com"
    assert sent["quotation"]["current"]["status"] == "sent"
    assert sent["quotation"]["current"]["valid_until"] is not None
    assert "#token=" in sent["approval_url"]
    assert sent["approval_url"] in outbox.outbox[-1].text
    assert "does not approve" in outbox.outbox[-1].text
    assert (
        owner_api.put(f"/quotations/{q['id']}/draft", json={"items": ITEMS(vat)}).status_code == 409
    )
    assert owner_api.post(f"/quotations/{q['id']}/send", json={}).status_code == 409


def test_send_requires_lines(owner_api: Api, job: dict[str, Any]) -> None:
    q = owner_api.post(f"/job-cards/{job['id']}/quotation").json()
    assert owner_api.post(f"/quotations/{q['id']}/send", json={}).status_code == 409


def test_viewing_link_is_not_approval(
    owner_api: Api, job: dict[str, Any], vat: str, new_api: Any, db: Session
) -> None:
    sent = _send(owner_api, _quote(owner_api, job, vat))
    customer: Api = new_api()
    view = customer.post("/public/quotations/view", json={"token": _token(sent["approval_url"])})
    assert view.status_code == 200
    page = view.json()
    assert page["status"] == "sent"
    assert page["can_decide"] is True
    assert page["total"] == "1742.25"
    assert "id" not in page  # no internal identifiers
    link = db.scalars(select(QuotationLink)).one()
    assert link.view_count == 1
    assert link.first_viewed_at is not None
    # The job is still blocked.
    assert (
        _move(owner_api, job["id"], "repair_in_progress").json()["error"]["code"]
        == "approval_required"
    )


def test_customer_approves_exact_version_and_total(
    owner_api: Api, job: dict[str, Any], vat: str, new_api: Any, db: Session
) -> None:
    sent = _send(owner_api, _quote(owner_api, job, vat))
    token = _token(sent["approval_url"])
    customer: Api = new_api()
    no_terms = customer.post(
        "/public/quotations/decision",
        json={"token": token, "decision": "approved", "customer_name": "Ndapewa Shikongo"},
    )
    assert no_terms.status_code == 422
    res = customer.post(
        "/public/quotations/decision",
        json={
            "token": token,
            "decision": "approved",
            "customer_name": "Ndapewa Shikongo",
            "accept_terms": True,
            "comments": "Go ahead",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["decision"] == "approved"
    assert res.json()["can_decide"] is False

    decision = db.scalars(select(QuotationDecision)).one()
    assert str(decision.total) == "1742.25"
    assert decision.method == "customer_link"
    assert decision.recorded_by_user_id is None
    assert (
        db.scalar(select(AuditLog.actor_type).where(AuditLog.action == "quotation.approved"))
        == "customer"
    )

    again = customer.post(
        "/public/quotations/decision",
        json={"token": token, "decision": "rejected", "customer_name": "Someone Else"},
    )
    assert again.status_code in (404, 409)
    # Viewing a used link still shows the outcome.
    assert (
        customer.post("/public/quotations/view", json={"token": token}).json()["decision"]
        == "approved"
    )

    detail = owner_api.get(f"/job-cards/{job['id']}").json()
    assert detail["approval_status"] == "quotation_approved"
    assert _move(owner_api, job["id"], "repair_in_progress").status_code == 200


def test_revision_supersedes_approval(
    owner_api: Api, job: dict[str, Any], vat: str, new_api: Any
) -> None:
    q = _quote(owner_api, job, vat)
    owner_api.post(f"/quotations/{q['id']}/send", json={"email_customer": False})
    owner_api.post(
        f"/quotations/{q['id']}/decisions",
        json={
            "decision": "approved",
            "method": "phone",
            "customer_name": "Ndapewa Shikongo",
            "evidence": "Phoned 081 234 5678 at 10:42",
        },
    )
    assert (
        owner_api.get(f"/job-cards/{job['id']}").json()["approval_status"] == "quotation_approved"
    )

    revised = owner_api.post(
        f"/quotations/{q['id']}/revisions", json={"reason": "Discs also need replacing"}
    ).json()
    assert revised["current"]["version_number"] == 2
    assert revised["current"]["status"] == "draft"
    assert len(revised["current"]["items"]) == 3  # copied
    assert [v["status"] for v in revised["versions"]] == ["draft", "superseded"]
    assert owner_api.get(f"/job-cards/{job['id']}").json()["approval_status"] == "not_required_yet"
    assert (
        _move(owner_api, job["id"], "repair_in_progress").json()["error"]["code"]
        == "approval_required"
    )
    assert (
        owner_api.post(f"/quotations/{q['id']}/revisions", json={"reason": "Again"}).status_code
        == 409
    )


def test_link_security(
    owner_api: Api, job: dict[str, Any], vat: str, new_api: Any, db: Session
) -> None:
    q = _quote(owner_api, job, vat)
    first = _token(_send(owner_api, q)["approval_url"])
    customer: Api = new_api()
    assert customer.post("/public/quotations/view", json={"token": "x" * 43}).status_code == 404

    second = _token(owner_api.post(f"/quotations/{q['id']}/links").json()["approval_url"])
    assert (
        customer.post("/public/quotations/view", json={"token": first}).status_code == 404
    )  # revoked
    assert customer.post("/public/quotations/view", json={"token": second}).status_code == 200

    db.execute(update(QuotationLink).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    db.commit()
    assert customer.post("/public/quotations/view", json={"token": second}).status_code == 404
    stored = db.scalars(select(QuotationLink.token_hash)).all()
    assert second not in stored


def test_expired_quotation_cannot_be_approved(
    owner_api: Api, job: dict[str, Any], vat: str, new_api: Any, db: Session
) -> None:
    q = _quote(owner_api, job, vat)
    token = _token(_send(owner_api, q)["approval_url"])
    db.execute(
        update(QuotationVersion).values(valid_until=datetime.now(UTC).date() - timedelta(days=1))
    )
    db.commit()
    assert owner_api.get(f"/quotations/{q['id']}").json()["current"]["status"] == "expired"
    staff = owner_api.post(
        f"/quotations/{q['id']}/decisions",
        json={
            "decision": "approved",
            "method": "in_person",
            "customer_name": "N S",
            "evidence": "Signed",
        },
    )
    assert staff.status_code == 409
    customer: Api = new_api()
    res = customer.post(
        "/public/quotations/decision",
        json={"token": token, "decision": "approved", "customer_name": "N S", "accept_terms": True},
    )
    assert res.status_code in (404, 409)
    assert (
        owner_api.post(f"/quotations/{q['id']}/revisions", json={"reason": "Re-quote"}).status_code
        == 200
    )


def test_staff_decision_rules(
    owner_api: Api, job: dict[str, Any], vat: str, org: OrgFixture, new_api: Any
) -> None:
    q = _quote(owner_api, job, vat)
    draft_decision = owner_api.post(
        f"/quotations/{q['id']}/decisions",
        json={
            "decision": "approved",
            "method": "phone",
            "customer_name": "N S",
            "evidence": "Call",
        },
    )
    assert draft_decision.status_code == 409  # not sent yet
    owner_api.post(f"/quotations/{q['id']}/send", json={"email_customer": False})
    assert (
        owner_api.post(
            f"/quotations/{q['id']}/decisions",
            json={"decision": "approved", "method": "phone", "customer_name": "N S"},
        ).status_code
        == 422
    )
    assert (
        owner_api.post(
            f"/quotations/{q['id']}/decisions",
            json={
                "decision": "approved",
                "method": "customer_link",
                "customer_name": "N S",
                "evidence": "x x x",
            },
        ).status_code
        == 422
    )

    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert mech.get(f"/quotations/{q['id']}").status_code == 404
    assert mech.get("/quotations").status_code == 403

    rejected = owner_api.post(
        f"/quotations/{q['id']}/decisions",
        json={
            "decision": "rejected",
            "method": "in_person",
            "customer_name": "Ndapewa Shikongo",
            "evidence": "Declined at counter",
            "comments": "Too expensive",
        },
    ).json()
    assert rejected["current"]["status"] == "rejected"
    assert rejected["current"]["decision"]["recorded_by"] == "Olivia Owner"
    assert owner_api.get("/quotations", params={"status": "rejected"}).json()["total"] == 1


def test_cross_organisation_quotations_invisible(
    owner_api: Api, job: dict[str, Any], vat: str, make_org: Any, new_api: Any
) -> None:
    q = _quote(owner_api, job, vat)
    other: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(other.owner_email)
    assert b.get(f"/quotations/{q['id']}").status_code == 404
    assert b.put(f"/quotations/{q['id']}/draft", json={"items": []}).status_code == 404
    assert b.post(f"/quotations/{q['id']}/send", json={}).status_code == 404
    assert b.post(f"/job-cards/{job['id']}/quotation").status_code == 404
    assert b.get("/quotations").json()["total"] == 0


def test_public_endpoints_rate_limited(
    owner_api: Api, job: dict[str, Any], vat: str, new_api: Any, settings_override: Any
) -> None:
    customer: Api = new_api()
    for _ in range(60):
        customer.post("/public/quotations/view", json={"token": "y" * 43})
    res = customer.post("/public/quotations/view", json={"token": "y" * 43})
    assert res.status_code == 429
    assert re.search("Too many", res.json()["error"]["message"])


def test_service_advisor_can_read_tax_rates_but_not_edit(
    owner_api: Api, vat: str, org: OrgFixture, new_api: Any
) -> None:
    org.add_user("advisor@example.com", [(org.role("service_advisor"), org.branch_id)])
    advisor: Api = new_api()
    advisor.login("advisor@example.com")
    assert [r["name"] for r in advisor.get("/organisation/tax-rates").json()] == ["Standard"]
    assert (
        advisor.patch(f"/organisation/tax-rates/{vat}", json={"rate_percent": "0"}).status_code
        == 403
    )
    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert mech.get("/organisation/tax-rates").status_code == 403
