"""Suppliers, purchase orders, partial deliveries, supplier returns."""

import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session

from tests.conftest import Api, OrgFixture
from tests.test_inventory import _ledger_matches, _main, _part


def _supplier(api: Api, name: str = "Windhoek Auto Parts") -> dict[str, Any]:
    res = api.post(
        "/suppliers", json={"name": name, "phone": "061 123 456", "email": "Sales@WAP.example"}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _order(
    api: Api, org: OrgFixture, supplier: dict[str, Any], lines: list[dict[str, Any]]
) -> dict[str, Any]:
    res = api.post(
        "/purchase-orders",
        json={"branch_id": str(org.branch_id), "supplier_id": supplier["id"], "lines": lines},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _approve(api: Api, po: dict[str, Any]) -> dict[str, Any]:
    res = api.post(f"/purchase-orders/{po['id']}/approve", json={"version": po["version"]})
    assert res.status_code == 200, res.text
    return res.json()


def _receive(
    api: Api,
    po: dict[str, Any],
    loc: str,
    lines: list[tuple[str, str]],
    key: str | None = None,
    **extra: Any,
) -> Any:
    return api.post(
        f"/purchase-orders/{po['id']}/receive",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={
            "location_id": loc,
            "lines": [{"po_line_id": lid, "quantity": q} for lid, q in lines],
            **extra,
        },
    )


def test_suppliers(owner_api: Api) -> None:
    s = _supplier(owner_api)
    assert s["email"] == "sales@wap.example"
    assert s["payment_terms_days"] == 30
    assert owner_api.post("/suppliers", json={"name": "windhoek auto parts"}).status_code == 409
    part = _part(owner_api)
    res = owner_api.put(
        f"/suppliers/{s['id']}/parts/{part['id']}",
        json={"supplier_sku": "WAP-778", "last_cost": "500.00", "lead_time_days": 3},
    )
    assert res.json()["parts"][0]["supplier_sku"] == "WAP-778"
    upd = owner_api.patch(f"/suppliers/{s['id']}", json={"payment_terms_days": 60, "email": None})
    assert (upd.json()["payment_terms_days"], upd.json()["email"]) == (60, None)
    assert owner_api.get("/suppliers", params={"search": "auto"}).json()["total"] == 1
    removed = owner_api.delete(f"/suppliers/{s['id']}/parts/{part['id']}")
    assert removed.json()["parts"] == []


def test_order_lifecycle_with_partial_delivery(
    owner_api: Api, org: OrgFixture, db: Session
) -> None:
    supplier = _supplier(owner_api)
    pads = _part(owner_api)
    oil = _part(owner_api, sku="OIL-5W30", unit="litre", cost_price="110.00")
    owner_api.put(
        f"/suppliers/{supplier['id']}/parts/{pads['id']}",
        json={"supplier_sku": "WAP-778", "last_cost": "500.00"},
    )
    po = _order(
        owner_api,
        org,
        supplier,
        [
            {"part_id": pads["id"], "quantity": "4"},
            {"part_id": oil["id"], "quantity": "20", "unit_cost": "105.50"},
        ],
    )
    assert po["po_number"] == "PO-000001"
    assert po["status"] == "draft"
    by_sku = {line["sku"]: line for line in po["lines"]}
    assert (by_sku["BP-1234"]["unit_cost"], by_sku["BP-1234"]["supplier_sku"]) == (
        "500.00",
        "WAP-778",
    )
    assert by_sku["OIL-5W30"]["line_total"] == "2110.00"
    assert po["total"] == "4110.00"

    loc = _main(owner_api)
    assert (
        _receive(owner_api, po, loc["id"], [(by_sku["BP-1234"]["id"], "1")]).status_code == 409
    )  # not approved
    stale = owner_api.post(
        f"/purchase-orders/{po['id']}/approve", json={"version": po["version"] + 5}
    )
    assert stale.status_code == 409
    po = _approve(owner_api, po)
    assert po["status"] == "approved"
    assert (
        owner_api.put(
            f"/purchase-orders/{po['id']}/draft", json={"version": po["version"], "lines": []}
        ).status_code
        == 409
    )

    # First delivery: 3 pads, 20 litres oil.
    res = _receive(
        owner_api,
        po,
        loc["id"],
        [(by_sku["BP-1234"]["id"], "3"), (by_sku["OIL-5W30"]["id"], "20")],
        delivery_reference="DN-5521",
        supplier_invoice_reference="INV-9001",
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["order"]["status"] == "partially_received"
    assert {(m["sku"], m["kind"], m["quantity"], m["unit_cost"]) for m in body["movements"]} == {
        ("BP-1234", "receipt", "3.00", "500.00"),
        ("OIL-5W30", "receipt", "20.00", "105.50"),
    }
    grn = body["order"]["receipts"][0]
    assert (grn["grn_number"], grn["total"], grn["supplier_invoice_reference"]) == (
        "GRN-000001",
        "3610.00",
        "INV-9001",
    )
    # Cost prices follow the received cost.
    assert owner_api.get(f"/inventory/parts/{oil['id']}").json()["cost_price"] == "105.50"
    assert owner_api.get(f"/inventory/parts/{pads['id']}").json()["stock"]["on_hand"] == "3.00"

    # Cannot receive more than outstanding.
    over = _receive(owner_api, po, loc["id"], [(by_sku["BP-1234"]["id"], "2")])
    assert over.status_code == 409
    assert "only 1.00 still to be received" in over.json()["error"]["message"]
    # Cannot cancel once something was received.
    cur = owner_api.get(f"/purchase-orders/{po['id']}").json()
    assert (
        owner_api.post(
            f"/purchase-orders/{po['id']}/cancel",
            json={"version": cur["version"], "reason": "No longer needed"},
        ).status_code
        == 409
    )

    # Last pad arrives -> received.
    done = _receive(owner_api, po, loc["id"], [(by_sku["BP-1234"]["id"], "1")], notes="Back-order")
    assert done.json()["order"]["status"] == "received"
    assert len(done.json()["order"]["receipts"]) == 2
    assert done.json()["order"]["received_value"] == "4110.00"
    assert _receive(owner_api, po, loc["id"], [(by_sku["BP-1234"]["id"], "1")]).status_code == 409

    supplier_view = owner_api.get(f"/suppliers/{supplier['id']}").json()
    assert supplier_view["received_value_90_days"] == "4110.00"
    assert {p["sku"]: p["last_cost"] for p in supplier_view["parts"]} == {
        "BP-1234": "500.00",
        "OIL-5W30": "105.50",
    }
    _ledger_matches(db)


def test_close_short_and_cancel(owner_api: Api, org: OrgFixture) -> None:
    supplier = _supplier(owner_api)
    part = _part(owner_api)
    loc = _main(owner_api)
    po = _approve(
        owner_api, _order(owner_api, org, supplier, [{"part_id": part["id"], "quantity": "5"}])
    )
    assert (
        owner_api.post(
            f"/purchase-orders/{po['id']}/close", json={"version": po["version"], "reason": "Short"}
        ).status_code
        == 409
    )
    po = _receive(owner_api, po, loc["id"], [(po["lines"][0]["id"], "2")]).json()["order"]
    closed = owner_api.post(
        f"/purchase-orders/{po['id']}/close",
        json={"version": po["version"], "reason": "Discontinued by supplier"},
    )
    assert closed.status_code == 200, closed.text
    assert (closed.json()["status"], closed.json()["closed_reason"]) == (
        "closed",
        "Discontinued by supplier",
    )
    assert (
        _receive(owner_api, closed.json(), loc["id"], [(po["lines"][0]["id"], "1")]).status_code
        == 409
    )

    other = _order(owner_api, org, supplier, [{"part_id": part["id"], "quantity": "1"}])
    res = owner_api.post(
        f"/purchase-orders/{other['id']}/cancel",
        json={"version": other["version"], "reason": "Ordered in error"},
    )
    assert res.json()["status"] == "cancelled"
    # Suppliers with open orders cannot be archived.
    open_po = _approve(
        owner_api, _order(owner_api, org, supplier, [{"part_id": part["id"], "quantity": "1"}])
    )
    assert owner_api.post(f"/suppliers/{supplier['id']}/archive").status_code == 409
    owner_api.post(
        f"/purchase-orders/{open_po['id']}/cancel",
        json={"version": open_po["version"], "reason": "Not needed"},
    )
    assert owner_api.post(f"/suppliers/{supplier['id']}/archive").status_code == 200
    assert (
        owner_api.post(
            "/purchase-orders",
            json={"branch_id": str(org.branch_id), "supplier_id": supplier["id"], "lines": []},
        ).status_code
        == 409
    )


def test_supplier_return(owner_api: Api, org: OrgFixture, db: Session) -> None:
    supplier = _supplier(owner_api)
    part = _part(owner_api)
    loc = _main(owner_api)
    po = _approve(
        owner_api, _order(owner_api, org, supplier, [{"part_id": part["id"], "quantity": "4"}])
    )
    line = po["lines"][0]["id"]
    _receive(owner_api, po, loc["id"], [(line, "4")])

    def ret(qty: str) -> Any:
        return owner_api.post(
            f"/purchase-orders/{po['id']}/returns",
            headers={"Idempotency-Key": uuid.uuid4().hex},
            json={
                "location_id": loc["id"],
                "reason": "Wrong part supplied",
                "reference": "RA-12",
                "lines": [{"po_line_id": line, "quantity": qty}],
            },
        )

    assert ret("5").status_code == 409
    res = ret("1")
    assert res.status_code == 201, res.text
    assert res.json()["movements"][0]["kind"] == "supplier_return"
    order = res.json()["order"]
    assert order["lines"][0]["quantity_returned"] == "1.00"
    assert order["returns"][0]["total"] == "520.00"
    assert order["returned_value"] == "520.00"
    assert owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]["on_hand"] == "3.00"
    assert ret("4").status_code == 409  # only 3 returnable
    _ledger_matches(db)


def test_receive_is_idempotent_and_concurrency_safe(
    owner_api: Api, org: OrgFixture, new_api: Any, db: Session
) -> None:
    supplier = _supplier(owner_api)
    part = _part(owner_api)
    loc = _main(owner_api)
    po = _approve(
        owner_api, _order(owner_api, org, supplier, [{"part_id": part["id"], "quantity": "3"}])
    )
    line = po["lines"][0]["id"]
    key = uuid.uuid4().hex
    first = _receive(owner_api, po, loc["id"], [(line, "1")], key=key)
    again = _receive(owner_api, po, loc["id"], [(line, "1")], key=key)
    assert (first.status_code, again.status_code) == (201, 200)
    assert len(again.json()["order"]["receipts"]) == 1

    apis = [new_api() for _ in range(4)]
    for a in apis:
        a.login(org.owner_email)
    results: list[int] = []

    def take(a: Api) -> None:
        results.append(_receive(a, po, loc["id"], [(line, "1")]).status_code)

    threads = [threading.Thread(target=take, args=(a,)) for a in apis]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 201, 409, 409]
    final = owner_api.get(f"/purchase-orders/{po['id']}").json()
    assert (final["status"], final["lines"][0]["quantity_received"]) == ("received", "3.00")
    assert owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]["on_hand"] == "3.00"


def test_permissions_and_scope(
    owner_api: Api, org: OrgFixture, new_api: Any, make_org: Any
) -> None:
    supplier = _supplier(owner_api)
    part = _part(owner_api)
    loc = _main(owner_api)

    org.add_user("stores@example.com", [(org.role("inventory_manager"), org.branch_id)])
    stores: Api = new_api()
    stores.login("stores@example.com")
    po = _order(stores, org, supplier, [{"part_id": part["id"], "quantity": "2"}])
    # Inventory managers prepare orders but do not approve them.
    assert (
        stores.post(
            f"/purchase-orders/{po['id']}/approve", json={"version": po["version"]}
        ).status_code
        == 403
    )
    assert stores.post("/suppliers", json={"name": "Other"}).status_code == 403  # catalogue-wide

    org.add_user("mgr@example.com", [(org.role("workshop_manager"), org.branch_id)])
    mgr: Api = new_api()
    mgr.login("mgr@example.com")
    po = _approve(mgr, po)
    assert _receive(stores, po, loc["id"], [(po["lines"][0]["id"], "2")]).status_code == 201

    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    assert mech.get("/purchase-orders").status_code == 403
    assert mech.get(f"/purchase-orders/{po['id']}").status_code == 404

    north = org.add_branch("WHK2", "Windhoek North")
    org.add_user("north@example.com", [(org.role("inventory_manager"), north.id)])
    other_branch: Api = new_api()
    other_branch.login("north@example.com")
    assert other_branch.get(f"/purchase-orders/{po['id']}").status_code == 404
    assert other_branch.get("/purchase-orders").json()["total"] == 0
    north_loc = next(x for x in other_branch.get("/inventory/locations").json() if x["is_default"])
    north_po = _approve(
        owner_api, _order(owner_api, org, supplier, [{"part_id": part["id"], "quantity": "1"}])
    )
    wrong = _receive(owner_api, north_po, north_loc["id"], [(north_po["lines"][0]["id"], "1")])
    assert wrong.status_code == 409  # location in another branch

    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert b.get(f"/suppliers/{supplier['id']}").status_code == 404
    assert b.get(f"/purchase-orders/{po['id']}").status_code == 404
    assert b.get("/suppliers").json()["total"] == 0
