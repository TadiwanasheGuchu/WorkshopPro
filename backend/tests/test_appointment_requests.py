"""Booking requests from the portal, staff confirmation, and service reminders."""

from datetime import timedelta
from typing import Any

from app.integrations.email import InMemoryEmailSender
from app.services import appointment_requests
from app.services.invoices import today
from tests.conftest import Api, OrgFixture
from tests.test_portal import _portal


def _setup(
    owner_api: Api,
    org: OrgFixture,
    new_api: Any,
    outbox: InMemoryEmailSender,
    name: str = "Haufiku",
    email: str = "h@example.com",
) -> tuple[Api, dict[str, Any], dict[str, Any]]:
    c = owner_api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "last_name": name,
            "contacts": [{"kind": "email", "value": email}],
            "preferred_contact_method": "email",
        },
    ).json()
    v = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": f"N {name[:3].upper()} R",
            "make": "Nissan",
            "model": "Navara",
        },
    ).json()
    return _portal(owner_api, new_api, outbox, c["id"], email), c, v


def _day(org: OrgFixture, days: int) -> str:
    return (today(org.db, org.id) + timedelta(days=days)).isoformat()


def _request(
    customer: Api, org: OrgFixture, vehicle_id: str | None, days: int = 3, **extra: Any
) -> Any:
    return customer.post(
        "/portal/appointment-requests",
        json={
            "branch_id": str(org.branch_id),
            "vehicle_id": vehicle_id,
            "preferred_date": _day(org, days),
            "time_of_day": "morning",
            "service_requested": "Major service",
            **extra,
        },
    )


def test_customer_requests_and_cancels(
    owner_api: Api, org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    customer, _c, v = _setup(owner_api, org, new_api, outbox)
    assert [b["name"] for b in customer.get("/portal/branches").json()] == ["Main branch"]
    res = _request(customer, org, v["id"])
    assert res.status_code == 201, res.text
    r = res.json()
    assert (r["status"], r["vehicle"]["name"], r["time_of_day"]) == (
        "pending",
        "N HAU R Nissan Navara",
        "morning",
    )
    assert _request(customer, org, v["id"], days=-1).status_code == 409
    assert _request(customer, org, v["id"], days=400).status_code == 409

    # Another customer's vehicle cannot be used.
    other, _, other_v = _setup(owner_api, org, new_api, outbox, "Nambahu", "n@example.com")
    assert _request(customer, org, other_v["id"]).status_code == 404
    assert other.get("/portal/appointment-requests").json() == []
    assert other.post(f"/portal/appointment-requests/{r['id']}/cancel").status_code == 404

    cancelled = customer.post(f"/portal/appointment-requests/{r['id']}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert customer.post(f"/portal/appointment-requests/{r['id']}/cancel").status_code == 409

    for _ in range(5):
        assert _request(customer, org, None).status_code == 201
    assert _request(customer, org, None).status_code == 409  # too many waiting


def test_staff_confirm_and_decline(
    owner_api: Api, org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    customer, _c, v = _setup(owner_api, org, new_api, outbox)
    r = _request(customer, org, v["id"]).json()
    pending = owner_api.get("/appointment-requests").json()
    assert [x["id"] for x in pending["items"]] == [r["id"]]

    res = owner_api.post(
        f"/appointment-requests/{r['id']}/confirm",
        json={"date": _day(org, 3), "start_time": "08:30", "duration_minutes": 120},
    )
    assert res.status_code == 200, res.text
    confirmed = res.json()
    assert (confirmed["status"], confirmed["decided_by"]) == ("confirmed", "Olivia Owner")
    appt = owner_api.get(f"/appointments/{confirmed['appointment_id']}").json()
    assert appt["reason"] == "Major service"
    mail = outbox.outbox[-1]
    assert mail.subject.startswith("Your booking at Kalahari Motors on ")
    assert "08:30" in mail.text
    assert (
        owner_api.post(
            f"/appointment-requests/{r['id']}/confirm",
            json={"date": _day(org, 3), "start_time": "09:00"},
        ).status_code
        == 409
    )

    mine = customer.get("/portal/appointment-requests").json()
    assert mine[0]["status"] == "confirmed"
    assert mine[0]["appointment_starts_at"] is not None

    r2 = _request(customer, org, v["id"], days=5).json()
    declined = owner_api.post(
        f"/appointment-requests/{r2['id']}/decline", json={"reason": "Fully booked that week"}
    )
    assert declined.json()["status"] == "declined"
    assert (
        customer.get("/portal/appointment-requests").json()[0]["decline_reason"]
        == "Fully booked that week"
    )


def test_confirmation_uses_booking_rules(
    owner_api: Api, org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    customer, c, v = _setup(owner_api, org, new_api, outbox)
    bay = owner_api.post(f"/branches/{org.branch_id}/service-bays", json={"name": "Bay 1"}).json()
    owner_api.post(
        "/appointments",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": c["id"],
            "date": _day(org, 3),
            "start_time": "08:00",
            "duration_minutes": 120,
            "service_bay_id": bay["id"],
            "reason": "Existing",
        },
    )
    r = _request(customer, org, v["id"]).json()
    clash = owner_api.post(
        f"/appointment-requests/{r['id']}/confirm",
        json={"date": _day(org, 3), "start_time": "09:00", "service_bay_id": bay["id"]},
    )
    assert clash.status_code == 409
    assert owner_api.get("/appointment-requests").json()["items"][0]["status"] == "pending"


def test_staff_permissions(
    owner_api: Api, org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender, make_org: Any
) -> None:
    customer, _c, v = _setup(owner_api, org, new_api, outbox)
    r = _request(customer, org, v["id"]).json()
    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert mech.get("/appointment-requests").status_code == 200
    assert (
        mech.post(
            f"/appointment-requests/{r['id']}/decline", json={"reason": "No thanks"}
        ).status_code
        == 403
    )
    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert b.get("/appointment-requests").json()["total"] == 0
    assert (
        b.post(f"/appointment-requests/{r['id']}/decline", json={"reason": "No thanks"}).status_code
        == 404
    )
    assert customer.get("/appointment-requests").status_code == 401  # portal session is not staff


def test_service_reminders_send_once(
    owner_api: Api, org: OrgFixture, outbox: InMemoryEmailSender
) -> None:
    c = owner_api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "last_name": "Kandjii",
            "contacts": [{"kind": "email", "value": "k@example.com"}],
        },
    ).json()
    soon = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 1 S",
            "make": "Toyota",
            "model": "Fortuner",
            "next_service_due_date": _day(org, 10),
        },
    ).json()
    owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 2 S",
            "make": "Toyota",
            "model": "Etios",
            "next_service_due_date": _day(org, 40),
        },
    )
    assert soon["next_service_due_date"] == _day(org, 10)

    assert appointment_requests.send_service_reminders() == 1
    assert outbox.outbox[-1].subject == "N 1 S Toyota Fortuner is due for a service"
    assert appointment_requests.send_service_reminders() == 0  # never twice

    # A new due date gets its own reminder; a longer window reaches the other vehicle.
    owner_api.patch(f"/vehicles/{soon['id']}", json={"next_service_due_date": _day(org, 5)})
    owner_api.patch("/organisation/settings", json={"service_reminder_days": 45})
    assert appointment_requests.send_service_reminders() == 2
    log = owner_api.get("/notifications", params={"event": "service_reminder"}).json()
    assert log["total"] == 3
