"""Customer portal: sign-in links, strict customer scoping, decisions, consent, revocation."""

# Fixtures are imported from other modules; pytest injects them by parameter name.
# ruff: noqa: F811

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.integrations.email import InMemoryEmailSender
from app.models import PortalToken, QuotationDecision
from tests.conftest import Api, OrgFixture
from tests.test_invoices import _issued, _pay, job, vat  # noqa: F401
from tests.test_quotations import ITEMS, _send


def _link(outbox: InMemoryEmailSender) -> str:
    text = outbox.outbox[-1].text
    return text.split("#token=")[1].split()[0]


def _add_email(api: Api, customer_id: str, email: str) -> None:
    c = api.get(f"/customers/{customer_id}").json()
    contacts = [{"kind": x["kind"], "value": x["value"]} for x in c["contacts"]] + [
        {"kind": "email", "value": email}
    ]
    res = api.patch(f"/customers/{customer_id}", json={"contacts": contacts})
    assert res.status_code == 200, res.text


def _portal(
    api: Api, new_api: Any, outbox: InMemoryEmailSender, customer_id: str, email: str
) -> Api:
    res = api.post(f"/customers/{customer_id}/portal/invite", json={"email": email})
    assert res.status_code == 200, res.text
    customer: Api = new_api()
    signed_in = customer.post("/portal/auth/consume", json={"token": _link(outbox)})
    assert signed_in.status_code == 204, signed_in.text
    return customer


def test_invite_and_single_use_link(
    owner_api: Api, job: dict[str, Any], new_api: Any, outbox: InMemoryEmailSender, db: Session
) -> None:
    cid = job["customer_id"]
    assert (
        owner_api.post(
            f"/customers/{cid}/portal/invite", json={"email": "someone@else.example"}
        ).status_code
        == 409
    )
    _add_email(owner_api, cid, "ndapewa@example.com")
    res = owner_api.post(f"/customers/{cid}/portal/invite", json={"email": "ndapewa@example.com"})
    assert res.json()["enabled"] is True
    mail = outbox.outbox[-1]
    assert mail.to == "ndapewa@example.com"
    assert "/portal/auth#token=" in mail.text
    token = _link(outbox)

    customer: Api = new_api()
    assert customer.get("/portal/home").status_code == 401
    assert customer.post("/portal/auth/consume", json={"token": token}).status_code == 204
    home = customer.get("/portal/home").json()
    assert home["me"]["customer_name"] == "Shikongo"
    assert [v["registration_number"] for v in home["vehicles"]] == ["N 9 W"]
    assert len(home["open_jobs"]) == 1

    again: Api = new_api()
    assert (
        again.post("/portal/auth/consume", json={"token": token}).status_code == 401
    )  # single use

    customer.post("/portal/auth/request-link", json={"email": "ndapewa@example.com"})
    db.execute(update(PortalToken).values(expires_at=utcnow()))
    db.commit()
    assert (
        again.post("/portal/auth/consume", json={"token": _link(outbox)}).status_code == 401
    )  # expired
    assert owner_api.get(f"/customers/{cid}/portal").json()["last_sign_in_at"] is not None


def test_request_link_does_not_reveal_accounts(
    owner_api: Api, job: dict[str, Any], new_api: Any, outbox: InMemoryEmailSender
) -> None:
    anon: Api = new_api()
    before = len(outbox.outbox)
    assert (
        anon.post("/portal/auth/request-link", json={"email": "nobody@example.com"}).status_code
        == 202
    )
    assert len(outbox.outbox) == before
    _add_email(owner_api, job["customer_id"], "ndapewa@example.com")
    owner_api.post(
        f"/customers/{job['customer_id']}/portal/invite", json={"email": "ndapewa@example.com"}
    )
    for _ in range(5):
        assert (
            anon.post(
                "/portal/auth/request-link", json={"email": "ndapewa@example.com"}
            ).status_code
            == 202
        )
    assert (
        anon.post("/portal/auth/request-link", json={"email": "ndapewa@example.com"}).status_code
        == 429
    )


def test_strict_customer_scoping(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    # Customer A owns `job` (with an approved quotation and an issued invoice).
    inv = _issued(owner_api, job)
    pay = _pay(owner_api, org, job["customer_id"], "10.00", [(inv["id"], "10.00")]).json()
    q = owner_api.get(f"/job-cards/{job['id']}/quotation").json()
    _add_email(owner_api, job["customer_id"], "a@example.com")
    a = _portal(owner_api, new_api, outbox, job["customer_id"], "a@example.com")

    # Customer B, with their own job.
    b_cust = owner_api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "last_name": "Other",
            "contacts": [{"kind": "email", "value": "b@example.com"}],
        },
    ).json()
    b_veh = owner_api.post(
        "/vehicles",
        json={
            "customer_id": b_cust["id"],
            "registration_number": "N 2 B",
            "make": "VW",
            "model": "Polo",
        },
    ).json()
    b_job = owner_api.post(
        "/job-cards",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": b_cust["id"],
            "vehicle_id": b_veh["id"],
            "complaint": "Noise",
        },
    ).json()
    b = _portal(owner_api, new_api, outbox, b_cust["id"], "b@example.com")

    assert a.get(f"/portal/jobs/{job['id']}").status_code == 200
    assert a.get(f"/portal/quotations/{q['id']}").status_code == 200
    assert a.get(f"/portal/invoices/{inv['id']}/pdf").headers["content-type"] == "application/pdf"
    assert a.get(f"/portal/receipts/{pay['id']}/pdf").status_code == 200
    assert [i["invoice_number"] for i in a.get("/portal/invoices").json()] == ["INV-000001"]

    for path in (
        f"/portal/jobs/{job['id']}",
        f"/portal/quotations/{q['id']}",
        f"/portal/quotations/{q['id']}/pdf",
        f"/portal/invoices/{inv['id']}/pdf",
        f"/portal/receipts/{pay['id']}/pdf",
        f"/portal/jobs/{uuid.uuid4()}",
    ):
        assert b.get(path).status_code == 404, path
    assert b.get("/portal/invoices").json() == []
    assert [j["job_number"] for j in b.get("/portal/jobs").json()] == [b_job["job_number"]]
    assert a.get(f"/portal/jobs/{b_job['id']}").status_code == 404

    # Portal sessions cannot reach staff endpoints, and staff sessions cannot use the portal.
    assert a.get("/customers").status_code == 401
    assert a.get(f"/invoices/{inv['id']}").status_code == 401
    assert owner_api.get("/portal/home").status_code == 401


def test_quotation_decision_in_portal(
    owner_api: Api,
    org: OrgFixture,
    vat: str,
    new_api: Any,
    outbox: InMemoryEmailSender,
    db: Session,
) -> None:
    c = owner_api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "last_name": "Amupolo",
            "contacts": [{"kind": "email", "value": "am@example.com"}],
        },
    ).json()
    v = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 7 Q",
            "make": "Ford",
            "model": "Ranger",
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
    owner_api.post(
        f"/job-cards/{j['id']}/transitions",
        json={"to_status": "diagnosis_in_progress", "version": 1},
    )
    q = owner_api.post(f"/job-cards/{j['id']}/quotation").json()
    owner_api.put(f"/quotations/{q['id']}/draft", json={"items": ITEMS(vat)})
    customer = _portal(owner_api, new_api, outbox, c["id"], "am@example.com")
    assert customer.get(f"/portal/quotations/{q['id']}").status_code == 404  # drafts are not shown

    _send(owner_api, q)
    assert [x["number"] for x in customer.get("/portal/home").json()["quotations_to_review"]] == [
        q["quote_number"]
    ]
    detail = customer.get(f"/portal/quotations/{q['id']}").json()
    assert (detail["status"], detail["total"], detail["can_decide"]) == ("sent", "1742.25", True)
    assert (
        customer.post(
            f"/portal/quotations/{q['id']}/decision", json={"decision": "approved"}
        ).status_code
        == 409
    )
    res = customer.post(
        f"/portal/quotations/{q['id']}/decision",
        json={"decision": "approved", "accept_terms": True, "comments": "Go ahead"},
    )
    assert res.status_code == 200, res.text
    assert (res.json()["decision"], res.json()["can_decide"]) == ("approved", False)
    d = db.scalars(select(QuotationDecision)).one()
    assert (d.method, d.customer_name, str(d.total)) == ("customer_portal", "Amupolo", "1742.25")
    assert "am@example.com" in (d.evidence or "")
    assert owner_api.get(f"/job-cards/{j['id']}").json()["approval_status"] == "quotation_approved"
    assert (
        customer.post(
            f"/portal/quotations/{q['id']}/decision", json={"decision": "rejected"}
        ).status_code
        == 409
    )


def test_profile_consent_csrf_and_revocation(
    owner_api: Api, job: dict[str, Any], new_api: Any, outbox: InMemoryEmailSender
) -> None:
    cid = job["customer_id"]
    _add_email(owner_api, cid, "ndapewa@example.com")
    customer = _portal(owner_api, new_api, outbox, cid, "ndapewa@example.com")
    me = customer.get("/portal/me").json()
    assert (me["whatsapp_consent"], me["email_consent"]) == (False, True)

    res = customer.patch(
        "/portal/me",
        json={
            "phone": "081 555 1234",
            "preferred_contact_method": "whatsapp",
            "whatsapp_consent": True,
        },
    )
    assert res.status_code == 200, res.text
    assert (res.json()["phone"], res.json()["whatsapp_consent"]) == ("0815551234", True)
    consents = owner_api.get(f"/customers/{cid}/consents").json()
    assert (consents[0]["channel"], consents[0]["status"], consents[0]["method"]) == (
        "whatsapp",
        "granted",
        "customer_portal",
    )
    assert owner_api.get(f"/customers/{cid}").json()["preferred_contact_method"] == "whatsapp"

    # CSRF: unsafe portal requests need the header.
    raw = customer.client.patch("/api/v1/portal/me", json={"preferred_contact_method": "email"})
    assert raw.status_code == 403

    assert owner_api.post(f"/customers/{cid}/portal/disable").json()["enabled"] is False
    assert customer.get("/portal/home").status_code == 401
    assert (
        customer.post(
            "/portal/auth/request-link", json={"email": "ndapewa@example.com"}
        ).status_code
        == 202
    )


def test_staff_permissions(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, new_api: Any, make_org: Any
) -> None:
    _add_email(owner_api, job["customer_id"], "ndapewa@example.com")
    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert (
        mech.post(
            f"/customers/{job['customer_id']}/portal/invite", json={"email": "ndapewa@example.com"}
        ).status_code
        == 403
    )
    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert b.get(f"/customers/{job['customer_id']}/portal").status_code == 404
