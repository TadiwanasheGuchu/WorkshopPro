"""Customer notifications: channel choice, consent, links never stored, retries, webhook."""

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.delivery import PermanentDeliveryError, TransientDeliveryError
from app.integrations.email import InMemoryEmailSender
from app.integrations.whatsapp import LogWhatsAppSender
from app.models import Notification
from app.services import notifications
from app.services.notifications import to_e164
from tests.conftest import Api, OrgFixture
from tests.test_quotations import ITEMS, _token


def _customer(
    api: Api,
    *,
    email: str | None = "ina@example.com",
    phone: str | None = "081 234 5678",
    preferred: str = "phone",
) -> dict[str, Any]:
    contacts = []
    if phone:
        contacts.append({"kind": "phone", "value": phone})
    if email:
        contacts.append({"kind": "email", "value": email})
    res = api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "last_name": "Nghifitikeko",
            "contacts": contacts,
            "preferred_contact_method": preferred,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _job(api: Api, org: OrgFixture, customer: dict[str, Any], reg: str = "N 55 W") -> Any:
    v = api.post(
        "/vehicles",
        json={
            "customer_id": customer["id"],
            "registration_number": reg,
            "make": "Toyota",
            "model": "Hilux",
        },
    ).json()
    return api.post(
        "/job-cards",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": customer["id"],
            "vehicle_id": v["id"],
            "complaint": "Service",
        },
    )


def _log(api: Api, **params: Any) -> list[dict[str, Any]]:
    res = api.get("/notifications", params=params)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _consent(api: Api, customer_id: str, channel: str, status: str = "granted") -> None:
    res = api.post(
        f"/customers/{customer_id}/consents",
        json={
            "channel": channel,
            "status": status,
            "method": "signed_form",
            "evidence": "Intake form",
        },
    )
    assert res.status_code == 201, res.text


def _enable_whatsapp(api: Api, event: str) -> None:
    t = next(x for x in api.get("/notification-templates").json() if x["event"] == event)
    res = api.put(
        f"/notification-templates/{event}",
        json={
            "is_enabled": True,
            "email_subject": t["email_subject"],
            "email_body": t["email_body"],
            "whatsapp_template_name": f"{event}_v1",
            "whatsapp_language": "en",
        },
    )
    assert res.status_code == 200, res.text


def test_vehicle_received_is_emailed(
    owner_api: Api, org: OrgFixture, outbox: InMemoryEmailSender
) -> None:
    c = _customer(owner_api)
    assert _job(owner_api, org, c).status_code == 201
    (n,) = _log(owner_api)
    assert (n["event"], n["channel"], n["status"], n["recipient"]) == (
        "vehicle_received",
        "email",
        "sent",
        "ina@example.com",
    )
    assert "N 55 W Toyota Hilux" in n["body"]
    (mail,) = outbox.outbox
    assert mail.subject == "We have received your vehicle N 55 W Toyota Hilux"


def test_whatsapp_needs_consent_template_and_phone(
    owner_api: Api, org: OrgFixture, whatsapp: LogWhatsAppSender, outbox: InMemoryEmailSender
) -> None:
    c = _customer(owner_api)
    _consent(owner_api, c["id"], "whatsapp")
    # No approved template configured yet: falls back to email.
    _job(owner_api, org, c)
    assert _log(owner_api)[0]["channel"] == "email"

    _enable_whatsapp(owner_api, "ready_for_collection")
    j = _job(owner_api, org, c, "N 56 W").json()
    for to in ("diagnosis_in_progress",):
        cur = owner_api.get(f"/job-cards/{j['id']}").json()
        owner_api.post(
            f"/job-cards/{j['id']}/transitions", json={"to_status": to, "version": cur["version"]}
        )
    owner_api.post(
        f"/job-cards/{j['id']}/approval-exceptions",
        json={"exception_type": "customer_verbal", "reason": "Phoned in", "scope": "Service"},
    )
    for to in ("repair_in_progress", "quality_inspection", "ready_for_collection"):
        cur = owner_api.get(f"/job-cards/{j['id']}").json()
        res = owner_api.post(
            f"/job-cards/{j['id']}/transitions", json={"to_status": to, "version": cur["version"]}
        )
        assert res.status_code == 200, res.text
    latest = _log(owner_api, event="ready_for_collection")[0]
    assert (latest["channel"], latest["recipient"], latest["status"], latest["provider"]) == (
        "whatsapp",
        "264812345678",
        "sent",
        "log",
    )
    (msg,) = whatsapp.sent
    assert (msg.template_name, msg.to) == ("ready_for_collection_v1", "264812345678")
    assert msg.params == ["Nghifitikeko", "N 56 W Toyota Hilux", "Kalahari Motors"]

    # Withdrawn consent: no WhatsApp.
    _consent(owner_api, c["id"], "whatsapp", "withdrawn")
    _job(owner_api, org, c, "N 57 W")
    assert _log(owner_api)[0]["channel"] == "email"


def test_preference_and_skips(owner_api: Api, org: OrgFixture) -> None:
    _enable_whatsapp(owner_api, "vehicle_received")
    email_first = _customer(owner_api, preferred="email")
    _consent(owner_api, email_first["id"], "whatsapp")
    _job(owner_api, org, email_first)
    assert _log(owner_api)[0]["channel"] == "email"

    nobody = _customer(owner_api, email=None, phone=None)
    _job(owner_api, org, nobody, "N 58 W")
    skipped = _log(owner_api)[0]
    assert skipped["status"] == "skipped"
    assert skipped["channel"] == "none"
    assert "no email address" in skipped["skip_reason"]

    withdrawn = _customer(owner_api, phone=None, email="w@example.com")
    _consent(owner_api, withdrawn["id"], "email", "withdrawn")
    _job(owner_api, org, withdrawn, "N 59 W")
    assert "email consent withdrawn" in _log(owner_api)[0]["skip_reason"].lower()


def test_quotation_link_is_sent_but_never_stored(
    owner_api: Api, org: OrgFixture, outbox: InMemoryEmailSender, db: Session
) -> None:
    c = _customer(owner_api)
    j = _job(owner_api, org, c).json()
    owner_api.post(
        f"/job-cards/{j['id']}/transitions",
        json={"to_status": "diagnosis_in_progress", "version": 1},
    )
    q = owner_api.post(f"/job-cards/{j['id']}/quotation").json()
    owner_api.put(f"/quotations/{q['id']}/draft", json={"items": ITEMS(None)})
    sent = owner_api.post(f"/quotations/{q['id']}/send", json={"email_customer": True}).json()
    assert (sent["emailed_to"], sent["notification_channel"]) == ("ina@example.com", "email")
    token = _token(sent["approval_url"])
    assert token in outbox.outbox[-1].text
    stored = db.scalars(select(Notification).where(Notification.event == "quotation_sent")).one()
    assert token not in stored.body
    assert "[customer link]" in stored.body
    assert stored.has_secret_link is True


def test_provider_outage_never_blocks_the_workshop(
    owner_api: Api, org: OrgFixture, outbox: InMemoryEmailSender
) -> None:
    c = _customer(owner_api)
    outbox.fail_with = TransientDeliveryError("SMTP timeout")
    assert _job(owner_api, org, c).status_code == 201  # the job is created regardless
    (n,) = _log(owner_api)
    assert (n["status"], n["attempts"], n["last_error"]) == ("queued", 1, "SMTP timeout")

    # The periodic sweep sends it once the provider is back.
    outbox.fail_with = None
    assert notifications.requeue_stale(older_than=timedelta(0)) == 1
    (n,) = _log(owner_api)
    assert (n["status"], n["attempts"]) == ("sent", 2)
    assert len(outbox.outbox) == 1


def test_final_attempt_and_permanent_failures(
    owner_api: Api, org: OrgFixture, outbox: InMemoryEmailSender
) -> None:
    c = _customer(owner_api)
    outbox.fail_with = PermanentDeliveryError("Mailbox does not exist")
    _job(owner_api, org, c)
    (n,) = _log(owner_api)
    assert (n["status"], n["last_error"], n["can_retry"]) == (
        "failed",
        "Mailbox does not exist",
        True,
    )

    outbox.fail_with = None
    res = owner_api.post(f"/notifications/{n['id']}/retry")
    assert res.status_code == 200, res.text
    assert _log(owner_api)[0]["status"] == "sent"
    assert owner_api.post(f"/notifications/{n['id']}/retry").status_code == 409  # not failed

    # A transient failure on the last attempt is recorded as failed.
    outbox.fail_with = TransientDeliveryError("still down")
    _job(owner_api, org, c, "N 60 W")
    queued = _log(owner_api, status="queued")[0]
    notifications.deliver(queued["id"], None, final_attempt=True)
    failed = _log(owner_api, status="failed")[0]
    assert failed["last_error"].startswith("Gave up after 2 attempts")


def test_failed_link_messages_cannot_be_retried(
    owner_api: Api, org: OrgFixture, outbox: InMemoryEmailSender
) -> None:
    c = _customer(owner_api)
    j = _job(owner_api, org, c).json()
    owner_api.post(
        f"/job-cards/{j['id']}/transitions",
        json={"to_status": "diagnosis_in_progress", "version": 1},
    )
    q = owner_api.post(f"/job-cards/{j['id']}/quotation").json()
    owner_api.put(f"/quotations/{q['id']}/draft", json={"items": ITEMS(None)})
    outbox.fail_with = PermanentDeliveryError("Rejected")
    owner_api.post(f"/quotations/{q['id']}/send", json={"email_customer": True})
    n = _log(owner_api, event="quotation_sent")[0]
    assert (n["status"], n["can_retry"]) == ("failed", False)
    res = owner_api.post(f"/notifications/{n['id']}/retry")
    assert res.status_code == 409
    assert "new link" in res.json()["error"]["message"]


def test_templates(
    owner_api: Api, org: OrgFixture, outbox: InMemoryEmailSender, new_api: Any
) -> None:
    templates = owner_api.get("/notification-templates").json()
    assert [t["event"] for t in templates] == [
        "vehicle_received",
        "quotation_sent",
        "ready_for_collection",
        "invoice_issued",
    ]
    t = templates[0]
    base = {
        "is_enabled": True,
        "email_subject": t["email_subject"],
        "whatsapp_template_name": None,
        "whatsapp_language": "en",
    }
    for bad in ("{customer_name.__class__}", "{customer_name!r}", "{quote_number}", "{nope}"):
        res = owner_api.put(
            "/notification-templates/vehicle_received", json={**base, "email_body": f"Hi {bad}"}
        )
        assert res.status_code == 409, bad
    ok = owner_api.put(
        "/notification-templates/vehicle_received",
        json={**base, "email_body": "Dear {customer_name}, {vehicle} arrived."},
    )
    assert ok.status_code == 200
    _job(owner_api, org, _customer(owner_api))
    assert outbox.outbox[-1].text == "Dear Nghifitikeko, N 55 W Toyota Hilux arrived."

    off = owner_api.put(
        "/notification-templates/vehicle_received",
        json={**base, "is_enabled": False, "email_body": "x {vehicle}"},
    )
    assert off.json()["is_enabled"] is False
    before = len(_log(owner_api))
    _job(owner_api, org, _customer(owner_api, email="b@example.com"), "N 61 W")
    assert len(_log(owner_api)) == before

    org.add_user("advisor@example.com", [(org.role("service_advisor"), org.branch_id)])
    advisor: Api = new_api()
    advisor.login("advisor@example.com")
    assert advisor.get("/notification-templates").status_code == 200
    assert (
        advisor.put(
            "/notification-templates/vehicle_received", json={**base, "email_body": "x"}
        ).status_code
        == 403
    )


def test_access(owner_api: Api, org: OrgFixture, new_api: Any, make_org: Any) -> None:
    _job(owner_api, org, _customer(owner_api))
    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert mech.get("/notifications").status_code == 403
    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert b.get("/notifications").json()["total"] == 0
    n = _log(owner_api)[0]
    assert b.post(f"/notifications/{n['id']}/retry").status_code == 404


def _signed(secret: str, payload: dict[str, Any]) -> tuple[bytes, str]:
    raw = json.dumps(payload).encode()
    return raw, "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_whatsapp_status_webhook(
    owner_api: Api, org: OrgFixture, new_api: Any, settings_override: Any
) -> None:
    _enable_whatsapp(owner_api, "vehicle_received")
    c = _customer(owner_api)
    _consent(owner_api, c["id"], "whatsapp")
    _job(owner_api, org, c)
    n = _log(owner_api)[0]
    assert n["channel"] == "whatsapp"
    provider_id = next(iter(org.db.scalars(select(Notification.provider_message_id))))
    payload = {
        "entry": [
            {"changes": [{"value": {"statuses": [{"id": provider_id, "status": "delivered"}]}}]}
        ]
    }
    meta: Api = new_api()  # no session, no CSRF cookie

    raw, sig = _signed("app-secret", payload)
    assert (
        meta.client.post(
            "/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig}
        ).status_code
        == 404
    )  # disabled
    settings_override(whatsapp_app_secret="app-secret", whatsapp_webhook_verify_token="verify-me")
    assert (
        meta.client.post(
            "/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": "sha256=bad"}
        ).status_code
        == 403
    )
    ok = meta.client.post(
        "/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"updated": 1}
    assert _log(owner_api)[0]["status"] == "delivered"
    # Status never goes backwards.
    raw2, sig2 = _signed(
        "app-secret",
        {
            "entry": [
                {"changes": [{"value": {"statuses": [{"id": provider_id, "status": "sent"}]}}]}
            ]
        },
    )
    assert meta.client.post(
        "/api/v1/webhooks/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2}
    ).json() == {"updated": 0}

    verify = meta.client.get(
        "/api/v1/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"},
    )
    assert (verify.status_code, verify.text) == (200, "12345")
    assert (
        meta.client.get(
            "/api/v1/webhooks/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    ("phone", "country", "expected"),
    [
        ("0812345678", "NA", "264812345678"),
        ("+264812345678", "NA", "264812345678"),
        ("0027821234567", "NA", "27821234567"),
        ("0821234567", "ZA", "27821234567"),
        ("812345678", "NA", None),
        ("0812345678", "XX", None),
    ],
)
def test_to_e164(phone: str, country: str, expected: str | None) -> None:
    assert to_e164(phone, country) == expected
