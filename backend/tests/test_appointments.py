from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.conftest import Api, OrgFixture

DAY = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()


@pytest.fixture
def ctx(org: OrgFixture, owner_api: Api) -> dict[str, Any]:
    c = owner_api.post(
        "/customers", json={"customer_type": "individual", "last_name": "Shikongo"}
    ).json()
    v = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 7 W",
            "make": "VW",
            "model": "Polo",
            "odometer_km": 40000,
        },
    ).json()
    bay = owner_api.post(f"/branches/{org.branch_id}/service-bays", json={"name": "Bay 1"}).json()
    mech = org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    return {
        "customer": c,
        "vehicle": v,
        "bay": bay,
        "mechanic": mech,
        "branch_id": str(org.branch_id),
    }


def _book(api: Api, ctx: dict[str, Any], **overrides: Any) -> Any:
    body = {
        "branch_id": ctx["branch_id"],
        "customer_id": ctx["customer"]["id"],
        "vehicle_id": ctx["vehicle"]["id"],
        "date": DAY,
        "start_time": "09:00",
        "duration_minutes": 90,
        "service_bay_id": ctx["bay"]["id"],
        "assigned_user_id": str(ctx["mechanic"].id),
        "reason": "Minor service",
        **overrides,
    }
    return api.post("/appointments", json=body)


def test_booking_uses_organisation_timezone(owner_api: Api, ctx: dict[str, Any]) -> None:
    res = _book(owner_api, ctx)
    assert res.status_code == 201, res.text
    appt = res.json()
    # Africa/Windhoek is UTC+2: 09:00 local is 07:00 UTC.
    assert datetime.fromisoformat(appt["starts_at"]).astimezone(UTC).hour == 7
    assert appt["local_start"] == "09:00:00"
    assert appt["local_end"] == "10:30:00"
    assert appt["assigned_user"]["name"] == "Mech"

    day = owner_api.get(
        "/appointments/day", params={"branch_id": ctx["branch_id"], "date": DAY}
    ).json()
    assert day["timezone"] == "Africa/Windhoek"
    assert [a["id"] for a in day["appointments"]] == [appt["id"]]
    assert [b["name"] for b in day["bays"]] == ["Bay 1"]


def test_overlapping_bay_or_mechanic_rejected(
    owner_api: Api, ctx: dict[str, Any], org: OrgFixture
) -> None:
    assert _book(owner_api, ctx).status_code == 201
    bay_clash = _book(owner_api, ctx, start_time="10:00", assigned_user_id=None)
    assert bay_clash.status_code == 409
    assert bay_clash.json()["error"]["details"]["conflict"] == "service bay"
    mech_clash = _book(owner_api, ctx, start_time="10:15", service_bay_id=None)
    assert mech_clash.json()["error"]["details"]["conflict"] == "mechanic"
    # Back-to-back is fine.
    assert _book(owner_api, ctx, start_time="10:30").status_code == 201
    # Cancelled bookings free the slot.
    other = _book(owner_api, ctx, start_time="12:00").json()
    owner_api.post(f"/appointments/{other['id']}/cancel", json={"reason": "Customer rescheduled"})
    assert _book(owner_api, ctx, start_time="12:00").status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_minutes": 7},
        {"duration_minutes": 0},
        {"reason": " "},
        {"start_time": "25:00"},
    ],
)
def test_invalid_bookings(owner_api: Api, ctx: dict[str, Any], overrides: dict[str, Any]) -> None:
    assert _book(owner_api, ctx, **overrides).status_code == 422


def test_booking_validates_references(owner_api: Api, ctx: dict[str, Any], org: OrgFixture) -> None:
    other = owner_api.post(
        "/customers", json={"customer_type": "individual", "last_name": "Other"}
    ).json()
    assert _book(owner_api, ctx, customer_id=other["id"]).status_code == 409  # vehicle not theirs
    advisor = org.add_user("advisor@example.com", [(org.role("service_advisor"), org.branch_id)])
    assert _book(owner_api, ctx, assigned_user_id=str(advisor.id)).status_code == 409
    elsewhere = org.add_branch("SWK")
    assert _book(owner_api, ctx, branch_id=str(elsewhere.id)).status_code == 409  # bay elsewhere


def test_reschedule_and_check_in(owner_api: Api, ctx: dict[str, Any], new_api: Any) -> None:
    appt = _book(owner_api, ctx).json()
    moved = owner_api.patch(f"/appointments/{appt['id']}", json={"start_time": "13:00"})
    assert moved.json()["local_start"] == "13:00:00"

    job = owner_api.post(
        f"/appointments/{appt['id']}/check-in",
        json={"intake_odometer_km": 40500, "fuel_level": "full"},
    )
    assert job.status_code == 201, job.text
    job = job.json()
    assert job["complaint"] == "Minor service"
    assert job["service_bay"]["name"] == "Bay 1"
    assert [a["name"] for a in job["assignees"]] == ["Mech"]
    after = owner_api.get(f"/appointments/{appt['id']}").json()
    assert after["status"] == "arrived"
    assert after["job_card"]["name"] == job["job_number"]
    assert owner_api.post(f"/appointments/{appt['id']}/check-in", json={}).status_code == 409
    assert (
        owner_api.patch(f"/appointments/{appt['id']}", json={"start_time": "15:00"}).status_code
        == 409
    )


def test_check_in_needs_vehicle(owner_api: Api, ctx: dict[str, Any]) -> None:
    appt = _book(owner_api, ctx, vehicle_id=None).json()
    res = owner_api.post(f"/appointments/{appt['id']}/check-in", json={})
    assert res.status_code == 409
    assert "vehicle" in res.json()["error"]["message"]


def test_permissions_and_isolation(
    owner_api: Api, ctx: dict[str, Any], new_api: Any, make_org: Any, org: OrgFixture
) -> None:
    appt = _book(owner_api, ctx).json()
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert (
        mech.get(
            "/appointments/day", params={"branch_id": ctx["branch_id"], "date": DAY}
        ).status_code
        == 200
    )
    assert _book(mech, ctx, start_time="15:00").status_code == 403
    assert (
        mech.post(f"/appointments/{appt['id']}/cancel", json={"reason": "nope"}).status_code == 403
    )

    other_branch = org.add_branch("WVB")
    org.add_user("far@example.com", [(org.role("service_advisor"), other_branch.id)])
    far: Api = new_api()
    far.login("far@example.com")
    assert far.get(f"/appointments/{appt['id']}").status_code == 404
    assert (
        far.get(
            "/appointments/day", params={"branch_id": ctx["branch_id"], "date": DAY}
        ).status_code
        == 403
    )

    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert b.get(f"/appointments/{appt['id']}").status_code == 404
    assert b.post(f"/appointments/{appt['id']}/check-in", json={}).status_code == 404
    # Another organisation's branch is reported as not found.
    assert (
        b.get("/appointments/day", params={"branch_id": ctx["branch_id"], "date": DAY}).status_code
        == 404
    )
