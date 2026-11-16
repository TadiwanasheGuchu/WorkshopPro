"""Reserving, issuing and returning parts for jobs."""

# Fixtures are imported from other modules; pytest injects them by parameter name.
# ruff: noqa: F811

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import Api, OrgFixture
from tests.test_inventory import _adjust, _ledger_matches, _main, _part, _transfer
from tests.test_invoices import job, vat  # noqa: F401
from tests.test_quotations import _move


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


def _reserve(api: Api, job_id: str, loc: str, part: str, qty: str, key: str | None = None) -> Any:
    return api.post(
        f"/job-cards/{job_id}/parts/reservations",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={"location_id": loc, "lines": [{"part_id": part, "quantity": qty}]},
    )


def _issue(api: Api, job_id: str, loc: str, part: str, qty: str) -> Any:
    return api.post(
        f"/job-cards/{job_id}/parts/issues",
        headers=_key(),
        json={"location_id": loc, "lines": [{"part_id": part, "quantity": qty}]},
    )


def _return(api: Api, job_id: str, loc: str, part: str, qty: str) -> Any:
    return api.post(
        f"/job-cards/{job_id}/parts/returns",
        headers=_key(),
        json={
            "location_id": loc,
            "reason": "Not needed",
            "lines": [{"part_id": part, "quantity": qty}],
        },
    )


def _reserved_matches(db: Session) -> None:
    """stock_levels.reserved equals what open reservations still hold."""
    mismatched = db.execute(
        text(
            "SELECT l.location_id, l.part_id FROM stock_levels l "
            "LEFT JOIN (SELECT location_id, part_id, "
            "sum(quantity - issued_quantity - released_quantity) q FROM stock_reservations "
            "WHERE status = 'open' GROUP BY 1, 2) r USING (location_id, part_id) "
            "WHERE l.reserved <> coalesce(r.q, 0)"
        )
    ).all()
    assert mismatched == []


def _new_job(api: Api, org: OrgFixture, reg: str) -> dict[str, Any]:
    c = api.post("/customers", json={"customer_type": "individual", "last_name": "Nangolo"}).json()
    v = api.post(
        "/vehicles",
        json={"customer_id": c["id"], "registration_number": reg, "make": "VW", "model": "Polo"},
    ).json()
    j = api.post(
        "/job-cards",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": c["id"],
            "vehicle_id": v["id"],
            "complaint": "Service",
        },
    ).json()
    _move(api, j["id"], "diagnosis_in_progress")
    return j


def _stocked(api: Api, qty: str = "5") -> tuple[dict[str, Any], dict[str, Any]]:
    part = _part(api)
    loc = _main(api)
    _adjust(api, loc["id"], [{"part_id": part["id"], "counted": qty}])
    return part, loc


def test_unauthorised_job_cannot_reserve_or_issue(owner_api: Api, org: OrgFixture) -> None:
    part, loc = _stocked(owner_api)
    j = _new_job(owner_api, org, "N 1 U")
    res = _reserve(owner_api, j["id"], loc["id"], part["id"], "1")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "approval_required"
    assert (
        _issue(owner_api, j["id"], loc["id"], part["id"], "1").json()["error"]["code"]
        == "approval_required"
    )
    parts = owner_api.get(f"/job-cards/{j['id']}/parts").json()
    assert parts["authorised"] is False
    assert parts["capabilities"]["reserve"] is False

    # An authorised exception makes the job authorised.
    owner_api.post(
        f"/job-cards/{j['id']}/approval-exceptions",
        json={
            "exception_type": "customer_verbal",
            "reason": "Customer phoned",
            "scope": "Replace filter",
        },
    )
    assert _reserve(owner_api, j["id"], loc["id"], part["id"], "1").status_code == 201


def test_reserve_issue_return(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, db: Session
) -> None:
    part, loc = _stocked(owner_api)
    res = _reserve(owner_api, job["id"], loc["id"], part["id"], "2")
    assert res.status_code == 201, res.text
    (r,) = res.json()["reservations"]
    assert (r["quantity"], r["outstanding"], r["status"]) == ("2.00", "2.00", "open")
    stock = owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]
    assert (stock["on_hand"], stock["reserved"], stock["available"]) == ("5.00", "2.00", "3.00")

    # Reserved stock cannot be taken by another job, transferred, or adjusted away.
    other = _new_job(owner_api, org, "N 2 U")
    owner_api.post(
        f"/job-cards/{other['id']}/approval-exceptions",
        json={"exception_type": "customer_verbal", "reason": "Customer phoned", "scope": "Filter"},
    )
    assert _reserve(owner_api, other["id"], loc["id"], part["id"], "4").status_code == 409
    van = owner_api.post(
        "/inventory/locations", json={"branch_id": str(org.branch_id), "name": "Van"}
    ).json()
    assert (
        _transfer(
            owner_api, loc["id"], van["id"], [{"part_id": part["id"], "quantity": "4"}]
        ).status_code
        == 409
    )
    assert (
        _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "1"}]).status_code == 409
    )

    # Issue 3: 2 from the reservation, 1 from free stock.
    res = _issue(owner_api, job["id"], loc["id"], part["id"], "3")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["reservations"][0]["status"] == "closed"
    assert body["reservations"][0]["issued_quantity"] == "2.00"
    assert body["used"] == [
        {
            "part": {"id": part["id"], "name": "Brake pad set"},
            "sku": "BP-1234",
            "unit": "each",
            "issued": "3.00",
            "selling_price": "890.00",
            "value": "2670.00",
        }
    ]
    assert body["movements"][0]["kind"] == "issue"
    assert body["movements"][0]["quantity"] == "-3.00"
    stock = owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]
    assert (stock["on_hand"], stock["reserved"], stock["available"]) == ("2.00", "0.00", "2.00")

    # Cannot issue more than is free.
    assert _issue(owner_api, job["id"], loc["id"], part["id"], "3").status_code == 409

    # Return at most what was issued.
    assert _return(owner_api, job["id"], loc["id"], part["id"], "4").status_code == 409
    res = _return(owner_api, job["id"], loc["id"], part["id"], "1")
    assert res.status_code == 201
    assert res.json()["used"][0]["issued"] == "2.00"
    assert owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]["on_hand"] == "3.00"
    movements = owner_api.get("/inventory/movements", params={"job_card_id": job["id"]}).json()
    assert [m["kind"] for m in movements["items"]] == ["return", "issue"]
    _ledger_matches(db)
    _reserved_matches(db)


def test_release_and_auto_release(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, db: Session
) -> None:
    part, loc = _stocked(owner_api)
    first = _reserve(owner_api, job["id"], loc["id"], part["id"], "1").json()["reservations"][0]
    _reserve(owner_api, job["id"], loc["id"], part["id"], "2")
    res = owner_api.post(
        f"/job-cards/{job['id']}/parts/reservations/{first['id']}/release",
        json={"reason": "Customer brought own"},
    )
    assert res.status_code == 200, res.text
    released = next(r for r in res.json()["reservations"] if r["id"] == first["id"])
    assert (released["status"], released["released_quantity"]) == ("closed", "1.00")
    assert (
        owner_api.post(
            f"/job-cards/{job['id']}/parts/reservations/{first['id']}/release",
            json={"reason": "Again"},
        ).status_code
        == 409
    )
    assert owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]["reserved"] == "2.00"

    # Completing the job releases the rest.
    _move(owner_api, job["id"], "ready_for_collection")
    j = owner_api.get(f"/job-cards/{job['id']}").json()
    done = owner_api.post(
        f"/job-cards/{job['id']}/transitions",
        json={"to_status": "completed", "version": j["version"], "collected_by_name": "Ndapewa"},
    )
    assert done.status_code == 200, done.text
    assert owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]["reserved"] == "0.00"
    parts = owner_api.get(f"/job-cards/{job['id']}/parts").json()
    assert all(r["status"] == "closed" for r in parts["reservations"])
    assert parts["capabilities"]["reserve"] is False
    _reserved_matches(db)


def test_cancelling_releases_reservations(owner_api: Api, org: OrgFixture, db: Session) -> None:
    part, loc = _stocked(owner_api)
    j = _new_job(owner_api, org, "N 3 U")
    owner_api.post(
        f"/job-cards/{j['id']}/approval-exceptions",
        json={"exception_type": "customer_verbal", "reason": "Customer phoned", "scope": "Filter"},
    )
    _reserve(owner_api, j["id"], loc["id"], part["id"], "3")
    cur = owner_api.get(f"/job-cards/{j['id']}").json()
    res = owner_api.post(
        f"/job-cards/{j['id']}/transitions",
        json={
            "to_status": "cancelled",
            "version": cur["version"],
            "cancellation_reason": "Customer declined",
        },
    )
    assert res.status_code == 200, res.text
    assert owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]["available"] == "5.00"
    _reserved_matches(db)


def test_rules_and_idempotency(owner_api: Api, job: dict[str, Any], org: OrgFixture) -> None:
    part, loc = _stocked(owner_api)
    north = org.add_branch("WHK2", "Windhoek North")
    north_loc = next(
        x
        for x in owner_api.get("/inventory/locations").json()
        if x["branch"]["id"] == str(north.id)
    )
    other_branch = _reserve(owner_api, job["id"], north_loc["id"], part["id"], "1")
    assert other_branch.status_code == 409
    assert "job's branch" in other_branch.json()["error"]["message"]

    key = uuid.uuid4().hex
    first = _reserve(owner_api, job["id"], loc["id"], part["id"], "1", key=key)
    again = _reserve(owner_api, job["id"], loc["id"], part["id"], "1", key=key)
    assert (first.status_code, again.status_code) == (201, 200)
    assert len(again.json()["reservations"]) == 1
    assert _reserve(owner_api, job["id"], loc["id"], part["id"], "2", key=key).status_code == 409
    assert (
        owner_api.post(
            f"/job-cards/{job['id']}/parts/issues",
            json={"location_id": loc["id"], "lines": [{"part_id": part["id"], "quantity": "1"}]},
        ).status_code
        == 422
    )


def test_permissions_and_scope(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, new_api: Any, make_org: Any
) -> None:
    part, loc = _stocked(owner_api)
    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    owner_api.post(
        f"/job-cards/{job['id']}/assignments",
        json={
            "user_id": str(
                org.db.execute(
                    text("SELECT id FROM users WHERE email = 'mech@example.com'")
                ).scalar()
            )
        },
    )
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert mech.get(f"/job-cards/{job['id']}/parts").status_code == 200
    assert _reserve(mech, job["id"], loc["id"], part["id"], "1").status_code == 403

    org.add_user("advisor@example.com", [(org.role("service_advisor"), org.branch_id)])
    advisor: Api = new_api()
    advisor.login("advisor@example.com")
    assert _issue(advisor, job["id"], loc["id"], part["id"], "1").status_code == 403

    org.add_user("stores@example.com", [(org.role("inventory_manager"), org.branch_id)])
    stores: Api = new_api()
    stores.login("stores@example.com")
    assert _issue(stores, job["id"], loc["id"], part["id"], "1").status_code == 201

    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert b.get(f"/job-cards/{job['id']}/parts").status_code == 404
    assert _reserve(b, job["id"], loc["id"], part["id"], "1").status_code == 404
