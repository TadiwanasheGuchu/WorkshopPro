"""Reports: figures, period handling, branch scope, permissions."""

# Fixtures are imported from test_invoices; pytest injects them by parameter name.
# ruff: noqa: F811

import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from tests.conftest import Api, OrgFixture
from tests.test_invoices import _issued, _pay, job, vat  # noqa: F401
from tests.test_quotations import _move


def _fin(api: Api, **params: Any) -> Any:
    today = datetime.now(ZoneInfo("Africa/Windhoek")).date()
    params.setdefault("date_from", (today - timedelta(days=1)).isoformat())
    params.setdefault("date_to", (today + timedelta(days=1)).isoformat())
    return api.get("/reports/financial", params=params)


def _ops(api: Api, **params: Any) -> Any:
    today = datetime.now(ZoneInfo("Africa/Windhoek")).date()
    params.setdefault("date_from", (today - timedelta(days=1)).isoformat())
    params.setdefault("date_to", (today + timedelta(days=1)).isoformat())
    return api.get("/reports/operations", params=params)


def test_financial_report_separates_invoiced_and_received(
    owner_api: Api, job: dict[str, Any], org: OrgFixture
) -> None:
    inv = _issued(owner_api, job)  # 1742.25
    owner_api.post(
        f"/invoices/{inv['id']}/credit-notes",
        json={
            "reason": "Goodwill",
            "lines": [{"description": "x", "quantity": "1", "unit_price": "42.25"}],
        },
    )
    _pay(owner_api, org, job["customer_id"], "1000.00", [(inv["id"], "1000.00")])
    deposit = _pay(owner_api, org, job["customer_id"], "300.00").json()  # unapplied
    mistake = _pay(owner_api, org, job["customer_id"], "50.00", method="cash").json()
    owner_api.post(
        f"/payments/{mistake['id']}/reverse",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={"reason": "Wrong customer"},
    )
    assert deposit["unallocated"] == "300.00"

    res = _fin(owner_api)
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["currency_code"] == "NAD"
    assert (r["invoiced"]["count"], r["invoiced"]["total"]) == (1, "1742.25")
    assert r["invoiced"]["subtotal"] == "1515.00"
    assert r["invoiced"]["tax_total"] == "227.25"
    assert r["credited"] == {"count": 1, "total": "42.25"}
    assert r["net_invoiced"] == "1700.00"
    assert r["received"] == {"count": 3, "total": "1350.00"}
    assert r["reversed"] == {"count": 1, "total": "50.00"}
    assert r["refunded"]["total"] == "0.00"
    assert r["net_received"] == "1300.00"
    methods = {m["method"]: m for m in r["by_method"]}
    assert methods["cash"] == {"method": "cash", "received": "50.00", "paid_out": "50.00"}
    assert sum(float(d["invoiced"]) for d in r["daily"]) == 1742.25

    rec = r["receivables"]
    assert rec["outstanding"] == "700.00"  # 1742.25 - 42.25 - 1000
    assert rec["open_invoices"] == 1
    assert rec["overdue"] == "0.00"  # due today
    assert rec["ageing"][0] == {"bucket": "Not yet due", "count": 1, "amount": "700.00"}
    assert rec["unapplied_credit"] == "300.00"  # the reversed 50 no longer counts
    assert {d["term"] for d in r["definitions"]} >= {"Invoiced", "Received", "Outstanding"}


def test_period_excludes_other_dates_and_drafts(owner_api: Api, job: dict[str, Any]) -> None:
    owner_api.post(f"/job-cards/{job['id']}/invoices")  # draft only
    r = _fin(owner_api).json()
    assert r["invoiced"]["count"] == 0
    past = _fin(owner_api, date_from="2020-01-01", date_to="2020-01-31").json()
    assert past["period"] == {
        "date_from": "2020-01-01",
        "date_to": "2020-01-31",
        "timezone": "Africa/Windhoek",
    }
    assert past["received"]["count"] == 0


def test_invalid_periods(owner_api: Api) -> None:
    assert _fin(owner_api, date_from="2026-02-01", date_to="2026-01-01").status_code == 422
    too_long = _fin(owner_api, date_from="2024-01-01", date_to="2025-12-31")
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "invalid_period"
    assert owner_api.get("/reports/financial").status_code == 422  # dates are required


def test_operations_report(owner_api: Api, job: dict[str, Any], org: OrgFixture) -> None:
    me = owner_api.get("/auth/me").json()
    owner_api.post(f"/job-cards/{job['id']}/assignments", json={"user_id": me["id"]})
    for to in ("ready_for_collection",):
        assert _move(owner_api, job["id"], to).status_code == 200
    j = owner_api.get(f"/job-cards/{job['id']}").json()
    done = owner_api.post(
        f"/job-cards/{job['id']}/transitions",
        json={"to_status": "completed", "version": j["version"], "collected_by_name": "Ndapewa"},
    )
    assert done.status_code == 200, done.text

    res = _ops(owner_api)
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["received"] == 1
    assert r["completed"] == 1
    assert r["cancelled"] == 0
    assert r["turnaround_hours_avg"] is not None
    assert r["open_total"] == 0
    assert r["quotations"]["sent"] == 1
    assert r["quotations"]["approved"] == 1
    assert r["quotations"]["approved_value"] == "1742.25"
    mech = {m["name"]: m for m in r["mechanics"]}
    assert mech[me["full_name"]]["completed_in_period"] == 1


def test_report_permissions_and_branch_scope(
    owner_api: Api, job: dict[str, Any], org: OrgFixture, new_api: Any, make_org: Any
) -> None:
    _issued(owner_api, job)

    org.add_user("advisor@example.com", [(org.role("service_advisor"), org.branch_id)])
    advisor: Api = new_api()
    advisor.login("advisor@example.com")
    assert _fin(advisor).status_code == 403
    assert _ops(advisor).status_code == 403

    org.add_user("acc@example.com", [(org.role("accounts"), org.branch_id)])
    acc: Api = new_api()
    acc.login("acc@example.com")
    assert _fin(acc).json()["invoiced"]["count"] == 1
    assert _ops(acc).status_code == 403

    # A manager of another branch sees nothing from this branch, and cannot ask for it.
    other = org.add_branch("WHK2")
    org.add_user("mgr@example.com", [(org.role("workshop_manager"), other.id)])
    mgr: Api = new_api()
    mgr.login("mgr@example.com")
    assert _fin(mgr).json()["invoiced"]["count"] == 0
    assert _fin(mgr, branch_id=str(org.branch_id)).status_code == 403
    scoped = _fin(mgr, branch_id=str(other.id)).json()
    assert scoped["branch"]["id"] == str(other.id)

    # Owner can filter by branch.
    assert _fin(owner_api, branch_id=str(other.id)).json()["invoiced"]["count"] == 0
    assert _fin(owner_api, branch_id=str(org.branch_id)).json()["invoiced"]["count"] == 1

    # Another organisation's branch is not found; its data never appears.
    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert _fin(b).json()["invoiced"]["count"] == 0
    assert _fin(b, branch_id=str(org.branch_id)).status_code == 404
