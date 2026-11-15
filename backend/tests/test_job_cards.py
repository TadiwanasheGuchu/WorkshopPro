from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, JobStatusHistory, Vehicle
from tests.conftest import Api, OrgFixture


@pytest.fixture
def setup(org: OrgFixture, owner_api: Api) -> dict[str, Any]:
    customer = owner_api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "first_name": "Ndapewa",
            "last_name": "Shikongo",
            "contacts": [{"kind": "phone", "value": "0812345678"}],
        },
    ).json()
    vehicle = owner_api.post(
        "/vehicles",
        json={
            "customer_id": customer["id"],
            "registration_number": "N 12345 W",
            "make": "Toyota",
            "model": "Hilux",
            "odometer_km": 120000,
        },
    ).json()
    return {"customer": customer, "vehicle": vehicle, "branch_id": str(org.branch_id)}


def _open_job(api: Api, setup: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body = {
        "branch_id": setup["branch_id"],
        "customer_id": setup["customer"]["id"],
        "vehicle_id": setup["vehicle"]["id"],
        "complaint": "Grinding noise when braking",
        "intake_odometer_km": 121500,
        "fuel_level": "half",
        **overrides,
    }
    res = api.post("/job-cards", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _move(api: Api, job: dict[str, Any], to: str, **extra: Any) -> Any:
    return api.post(
        f"/job-cards/{job['id']}/transitions",
        json={"to_status": to, "version": job["version"], **extra},
    )


def _step(api: Api, job: dict[str, Any], to: str, **extra: Any) -> dict[str, Any]:
    res = _move(api, job, to, **extra)
    assert res.status_code == 200, res.text
    return res.json()


def _exception(api: Api, job: dict[str, Any]) -> dict[str, Any]:
    res = api.post(
        f"/job-cards/{job['id']}/approval-exceptions",
        json={
            "exception_type": "customer_verbal",
            "reason": "Customer approved by phone; written quotation follows",
            "scope": "Replace front brake pads and skim discs",
            "customer_contact": "Ndapewa Shikongo, 081 234 5678",
            "max_amount": "2500.00",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- intake


def test_receive_vehicle_allocates_numbers_and_records_history(
    owner_api: Api, setup: dict[str, Any], db: Session
) -> None:
    job = _open_job(owner_api, setup)

    assert job["job_number"] == "JC-000001"
    assert job["status"] == "vehicle_received"
    assert job["status_label"] == "Vehicle received"
    assert job["received_by"] == "Olivia Owner"
    assert [h["to_status"] for h in job["status_history"]] == ["vehicle_received"]
    assert db.scalar(select(Vehicle.odometer_km)) == 121500

    owner_api.post(
        f"/job-cards/{job['id']}/transitions",
        json={"to_status": "cancelled", "version": 1, "cancellation_reason": "Customer left"},
    )
    second = _open_job(owner_api, setup, intake_odometer_km=121600)
    assert second["job_number"] == "JC-000002"


def test_intake_validation(owner_api: Api, setup: dict[str, Any], org: OrgFixture) -> None:
    lower = owner_api.post("/job-cards", json={**_base(setup), "intake_odometer_km": 1000})
    assert lower.status_code == 422
    assert lower.json()["error"]["code"] == "odometer_decrease"
    ok = owner_api.post(
        "/job-cards",
        json={
            **_base(setup),
            "intake_odometer_km": 1000,
            "odometer_correction_reason": "Cluster replaced",
        },
    )
    assert ok.status_code == 201

    again = owner_api.post("/job-cards", json=_base(setup))
    assert again.status_code == 409
    assert again.json()["error"]["details"]["open_job_number"] == "JC-000001"

    other = owner_api.post(
        "/customers", json={"customer_type": "individual", "last_name": "Other"}
    ).json()
    mismatch = owner_api.post("/job-cards", json={**_base(setup), "customer_id": other["id"]})
    assert mismatch.status_code == 409
    assert owner_api.post("/job-cards", json={**_base(setup), "complaint": "  "}).status_code == 422


def _base(setup: dict[str, Any]) -> dict[str, Any]:
    return {
        "branch_id": setup["branch_id"],
        "customer_id": setup["customer"]["id"],
        "vehicle_id": setup["vehicle"]["id"],
        "complaint": "Service",
    }


# --------------------------------------------------------------------------- workflow


def test_invalid_transition_rejected(owner_api: Api, setup: dict[str, Any]) -> None:
    job = _open_job(owner_api, setup)
    res = _move(owner_api, job, "completed", collected_by_name="X")
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["code"] == "invalid_state_transition"
    assert "diagnosis_in_progress" in error["details"]["allowed"]
    assert _move(owner_api, job, "flying").status_code == 422


def test_repair_cannot_start_without_approval(owner_api: Api, setup: dict[str, Any]) -> None:
    job = _step(owner_api, _open_job(owner_api, setup), "diagnosis_in_progress")
    job = _step(owner_api, job, "awaiting_approval")

    blocked = _move(owner_api, job, "repair_in_progress")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "approval_required"
    parts = _move(owner_api, job, "awaiting_parts")
    assert parts.json()["error"]["code"] == "approval_required"

    detail = owner_api.get(f"/job-cards/{job['id']}").json()
    repair = next(
        t for t in detail["capabilities"]["transitions"] if t["to_status"] == "repair_in_progress"
    )
    assert repair["allowed"] is False
    assert "approved quotation" in repair["reason"]

    job = _exception(owner_api, job)
    assert job["approval_status"] == "exception_active"
    assert job["approval_exceptions"][0]["authorised_by"] == "Olivia Owner"
    assert job["approval_exceptions"][0]["max_amount"] == "2500.00"
    job = _step(owner_api, job, "repair_in_progress")
    assert job["status"] == "repair_in_progress"


def test_revoked_exception_no_longer_authorises(owner_api: Api, setup: dict[str, Any]) -> None:
    job = _step(owner_api, _open_job(owner_api, setup), "diagnosis_in_progress")
    job = _exception(owner_api, job)
    exc_id = job["approval_exceptions"][0]["id"]
    res = owner_api.post(
        f"/job-cards/{job['id']}/approval-exceptions/{exc_id}/revoke",
        json={"reason": "Customer withdrew approval"},
    )
    job = res.json()
    assert job["approval_exceptions"][0]["revoke_reason"] == "Customer withdrew approval"
    assert (
        _move(owner_api, job, "repair_in_progress").json()["error"]["code"] == "approval_required"
    )
    again = owner_api.post(
        f"/job-cards/{job['id']}/approval-exceptions/{exc_id}/revoke", json={"reason": "Twice"}
    )
    assert again.status_code == 409


def test_full_lifecycle_to_collection(owner_api: Api, setup: dict[str, Any], db: Session) -> None:
    job = _open_job(owner_api, setup)
    job = _step(owner_api, job, "inspection_pending")
    job = _step(owner_api, job, "diagnosis_in_progress")
    job = _exception(owner_api, job)
    job = _step(owner_api, job, "repair_in_progress")
    job = _step(owner_api, job, "awaiting_parts", note="Pads on order from supplier")
    job = _step(owner_api, job, "repair_in_progress")
    job = _step(owner_api, job, "quality_inspection")
    job = _step(owner_api, job, "repair_in_progress", note="Squeal on test drive")
    job = _step(owner_api, job, "quality_inspection")
    job = _step(owner_api, job, "ready_for_collection")

    missing = _move(owner_api, job, "completed")
    assert missing.status_code == 422
    job = _step(
        owner_api,
        job,
        "completed",
        collected_by_name="Ndapewa Shikongo",
        handover_notes="Old pads returned",
    )

    assert job["collected_at"] is not None
    assert job["capabilities"]["transitions"] == []
    assert job["capabilities"]["edit_details"] is False
    history = [h["to_status"] for h in job["status_history"]]
    assert history[0] == "vehicle_received"
    assert history[-1] == "completed"
    assert len(history) == 11
    assert job["status_history"][4]["note"] == "Pads on order from supplier"
    edit = owner_api.patch(
        f"/job-cards/{job['id']}", json={"version": job["version"], "priority": "low"}
    )
    assert edit.status_code == 409
    audits = db.scalars(
        select(AuditLog.action).where(AuditLog.action == "job_card.status_changed")
    ).all()
    assert len(audits) == 10


def test_cancel_requires_reason(owner_api: Api, setup: dict[str, Any]) -> None:
    job = _open_job(owner_api, setup)
    assert _move(owner_api, job, "cancelled").status_code == 422
    job = _step(owner_api, job, "cancelled", cancellation_reason="Customer took vehicle elsewhere")
    assert job["cancellation_reason"] == "Customer took vehicle elsewhere"
    # Cancelled jobs free the vehicle for a new job card.
    assert owner_api.post("/job-cards", json=_base(setup)).status_code == 201


def test_stale_version_rejected(owner_api: Api, setup: dict[str, Any]) -> None:
    job = _open_job(owner_api, setup)
    first = owner_api.patch(f"/job-cards/{job['id']}", json={"version": 1, "priority": "urgent"})
    assert first.status_code == 200
    stale = owner_api.patch(f"/job-cards/{job['id']}", json={"version": 1, "priority": "low"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_version"
    assert _move(owner_api, job, "diagnosis_in_progress").json()["error"]["code"] == "stale_version"


def test_history_is_recorded_per_transition(
    owner_api: Api, setup: dict[str, Any], db: Session
) -> None:
    job = _step(owner_api, _open_job(owner_api, setup), "diagnosis_in_progress", note="Starting")
    rows = db.scalars(select(JobStatusHistory).order_by(JobStatusHistory.changed_at)).all()
    assert [(r.from_status, r.to_status) for r in rows] == [
        (None, "vehicle_received"),
        ("vehicle_received", "diagnosis_in_progress"),
    ]
    assert rows[1].note == "Starting"
    assert job["status_history"][1]["changed_by"] == "Olivia Owner"


# --------------------------------------------------------------------------- mechanics


@pytest.fixture
def mechanic(org: OrgFixture, new_api: Any) -> tuple[Api, Any]:
    user = org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    api: Api = new_api()
    assert api.login("mech@example.com").status_code == 204
    return api, user


def test_mechanic_sees_only_assigned_jobs(
    owner_api: Api, setup: dict[str, Any], mechanic: Any
) -> None:
    mech, user = mechanic
    job = _open_job(owner_api, setup)

    assert mech.get("/job-cards").json()["total"] == 0
    assert mech.get(f"/job-cards/{job['id']}").status_code == 404

    assignable = owner_api.get(f"/job-cards/{job['id']}/assignable-users").json()
    # Owners hold every permission, so they are assignable too (small workshops).
    assert {u["full_name"] for u in assignable} == {"Mech", "Olivia Owner"}
    job = owner_api.post(
        f"/job-cards/{job['id']}/assignments", json={"user_id": str(user.id)}
    ).json()
    assert [a["name"] for a in job["assignees"]] == ["Mech"]

    listed = mech.get("/job-cards", params={"assigned_to_me": True}).json()
    assert [j["job_number"] for j in listed["items"]] == ["JC-000001"]
    detail = mech.get(f"/job-cards/{job['id']}").json()
    assert detail["capabilities"]["edit_work"] is True
    assert detail["capabilities"]["edit_details"] is False
    assert [t["to_status"] for t in detail["capabilities"]["transitions"]] == [
        "diagnosis_in_progress"
    ]

    owner_api.delete(f"/job-cards/{job['id']}/assignments/{user.id}")
    assert mech.get(f"/job-cards/{job['id']}").status_code == 404


def test_mechanic_limited_transitions_and_fields(
    owner_api: Api, setup: dict[str, Any], mechanic: Any
) -> None:
    mech, user = mechanic
    job = _open_job(owner_api, setup)
    owner_api.post(f"/job-cards/{job['id']}/assignments", json={"user_id": str(user.id)})
    job = mech.get(f"/job-cards/{job['id']}").json()

    job = _step(mech, job, "diagnosis_in_progress")
    updated = mech.patch(
        f"/job-cards/{job['id']}",
        json={"version": job["version"], "diagnosis": "Pads worn to metal"},
    )
    assert updated.status_code == 200
    job = updated.json()
    assert (
        mech.patch(
            f"/job-cards/{job['id']}", json={"version": job["version"], "priority": "urgent"}
        ).status_code
        == 403
    )
    assert (
        mech.post(f"/job-cards/{job['id']}/notes", json={"body": "Front discs scored"}).status_code
        == 201
    )
    assert _move(mech, job, "cancelled", cancellation_reason="no").status_code == 403
    assert (
        mech.post(
            f"/job-cards/{job['id']}/approval-exceptions",
            json={"exception_type": "other", "reason": "Because", "scope": "Everything"},
        ).status_code
        == 403
    )

    job = _exception(owner_api, job)
    job = _step(mech, job, "repair_in_progress")
    job = _step(mech, job, "quality_inspection")
    # Quality sign-off is a manager decision.
    assert _move(mech, job, "ready_for_collection").status_code == 403
    job = _step(owner_api, job, "ready_for_collection")
    assert job["status"] == "ready_for_collection"


def test_only_workers_at_branch_can_be_assigned(
    owner_api: Api, setup: dict[str, Any], org: OrgFixture
) -> None:
    job = _open_job(owner_api, setup)
    other_branch = org.add_branch("SWK")
    elsewhere = org.add_user("far@example.com", [(org.role("mechanic"), other_branch.id)])
    advisor = org.add_user("advisor@example.com", [(org.role("service_advisor"), org.branch_id)])
    invited = org.add_user(
        "new@example.com", [(org.role("mechanic"), org.branch_id)], password=None
    )

    for user in (elsewhere, advisor, invited):
        res = owner_api.post(f"/job-cards/{job['id']}/assignments", json={"user_id": str(user.id)})
        assert res.status_code == 409, user.email
    mech = org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    assert (
        owner_api.post(
            f"/job-cards/{job['id']}/assignments", json={"user_id": str(mech.id)}
        ).status_code
        == 200
    )
    dup = owner_api.post(f"/job-cards/{job['id']}/assignments", json={"user_id": str(mech.id)})
    assert dup.status_code == 409


# --------------------------------------------------------------------------- scoping


def test_branch_scoped_manager_sees_only_own_branch(
    owner_api: Api, setup: dict[str, Any], org: OrgFixture, new_api: Any
) -> None:
    other = org.add_branch("SWK", "Swakopmund")
    org.add_user("mgr@example.com", [(org.role("workshop_manager"), other.id)])
    mgr: Api = new_api()
    mgr.login("mgr@example.com")
    job = _open_job(owner_api, setup)

    assert mgr.get(f"/job-cards/{job['id']}").status_code == 404
    assert mgr.get("/job-cards").json()["total"] == 0
    assert mgr.post("/job-cards", json=_base(setup)).status_code == 403  # main branch
    own = mgr.post("/job-cards", json={**_base(setup), "branch_id": str(other.id)})
    assert (
        own.status_code == 409
    )  # vehicle already has open job at main branch — visible only by number
    assert mgr.get("/job-cards/summary").json()["open_total"] == 0


def test_cross_organisation_job_cards_invisible(make_org: Any, new_api: Any) -> None:
    org_a: OrgFixture = make_org("Alpha")
    org_b: OrgFixture = make_org("Beta")
    a: Api = new_api()
    a.login(org_a.owner_email)
    b: Api = new_api()
    b.login(org_b.owner_email)
    customer = a.post("/customers", json={"customer_type": "individual", "last_name": "A"}).json()
    vehicle = a.post(
        "/vehicles",
        json={
            "customer_id": customer["id"],
            "registration_number": "N 1 A",
            "make": "VW",
            "model": "Polo",
        },
    ).json()
    setup = {"customer": customer, "vehicle": vehicle, "branch_id": str(org_a.branch_id)}
    job = _open_job(a, setup, intake_odometer_km=None)

    assert b.get(f"/job-cards/{job['id']}").status_code == 404
    assert _move(b, job, "diagnosis_in_progress").status_code == 404
    assert b.post(f"/job-cards/{job['id']}/notes", json={"body": "x"}).status_code == 404
    assert b.get("/job-cards").json()["total"] == 0
    # B cannot open a job in A's branch or for A's vehicle.
    assert b.post("/job-cards", json={**_base(setup)}).status_code in (403, 404)
    b_cust = b.post("/customers", json={"customer_type": "individual", "last_name": "B"}).json()
    res = b.post(
        "/job-cards",
        json={**_base(setup), "branch_id": str(org_b.branch_id), "customer_id": b_cust["id"]},
    )
    assert res.status_code == 404


# --------------------------------------------------------------------------- summary


def test_summary_counts(owner_api: Api, setup: dict[str, Any], db: Session) -> None:
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    job = _open_job(owner_api, setup, promised_at=past, priority="urgent")
    counts = owner_api.get("/job-cards/summary").json()
    assert counts["open_total"] == 1
    assert counts["received_today"] == 1
    assert counts["overdue"] == 1
    assert counts["by_status"]["vehicle_received"] == 1
    listed = owner_api.get("/job-cards", params={"overdue": True}).json()
    assert listed["items"][0]["is_overdue"] is True
    assert owner_api.get("/job-cards", params={"search": "n12345"}).json()["total"] == 1
    assert owner_api.get("/job-cards", params={"search": "JC-000001"}).json()["total"] == 1
    assert owner_api.get("/job-cards", params={"status": "completed"}).json()["total"] == 0
    assert job["is_overdue"] is True
