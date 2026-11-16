"""Parts catalogue, stock ledger integrity, adjustments, transfers, permissions."""

import threading
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models import StockLevel, StockMovement
from tests.conftest import Api, OrgFixture


def _part(api: Api, sku: str = "BP-1234", **extra: Any) -> dict[str, Any]:
    res = api.post(
        "/inventory/parts",
        json={
            "sku": sku,
            "name": "Brake pad set",
            "cost_price": "520.00",
            "selling_price": "890.00",
            **extra,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _main(api: Api) -> dict[str, Any]:
    return next(loc for loc in api.get("/inventory/locations").json() if loc["is_default"])


def _adjust(
    api: Api,
    location_id: str,
    lines: list[dict[str, Any]],
    key: str | None = None,
    reason: str = "Stocktake",
) -> Any:
    return api.post(
        "/inventory/adjustments",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={"location_id": location_id, "reason": reason, "lines": lines},
    )


def _transfer(api: Api, src: str, dst: str, lines: list[dict[str, Any]]) -> Any:
    return api.post(
        "/inventory/transfers",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={"from_location_id": src, "to_location_id": dst, "lines": lines},
    )


def _ledger_matches(db: Session) -> None:
    """stock_levels.on_hand equals the sum of movements for every part and location."""
    mismatched = db.execute(
        text(
            "SELECT l.location_id, l.part_id FROM stock_levels l "
            "LEFT JOIN (SELECT location_id, part_id, sum(quantity) q FROM stock_movements "
            "GROUP BY 1, 2) m USING (location_id, part_id) "
            "WHERE l.on_hand <> coalesce(m.q, 0)"
        )
    ).all()
    assert mismatched == []


# --------------------------------------------------------------------------- catalogue


def test_catalogue_and_unique_sku(owner_api: Api) -> None:
    cat = owner_api.post("/inventory/categories", json={"name": "Brakes"}).json()
    part = _part(owner_api, category_id=cat["id"], unit="set")
    assert part["category"]["name"] == "Brakes"
    assert part["cost_price"] == "520.00"
    assert part["stock"] == {
        "on_hand": "0.00",
        "reserved": "0.00",
        "available": "0.00",
        "low_locations": 0,
    }
    assert (
        owner_api.post("/inventory/parts", json={"sku": "bp-1234", "name": "Dup"}).status_code
        == 409
    )
    assert owner_api.post("/inventory/categories", json={"name": "brakes"}).status_code == 409

    res = owner_api.patch(f"/inventory/parts/{part['id']}", json={"selling_price": "950.00"})
    assert res.json()["selling_price"] == "950.00"
    assert owner_api.patch(f"/inventory/parts/{part['id']}", json={"sku": None}).status_code == 422
    found = owner_api.get("/inventory/parts", params={"search": "pad"}).json()
    assert [p["sku"] for p in found["items"]] == ["BP-1234"]
    assert owner_api.get("/inventory/categories").json()[0]["part_count"] == 1


def test_each_branch_has_a_default_location(owner_api: Api, org: OrgFixture) -> None:
    org.add_branch("WHK2", "Windhoek North")
    locations = owner_api.get("/inventory/locations").json()
    assert sorted((loc["branch"]["name"], loc["name"], loc["is_default"]) for loc in locations) == [
        ("Main branch", "Main store", True),
        ("Windhoek North", "Main store", True),
    ]


# --------------------------------------------------------------------------- ledger


def test_opening_stock_then_stocktake(owner_api: Api, db: Session) -> None:
    part = _part(owner_api)
    loc = _main(owner_api)
    res = _adjust(
        owner_api, loc["id"], [{"part_id": part["id"], "counted": "10"}], reason="Opening count"
    )
    assert res.status_code == 201, res.text
    (m,) = res.json()["movements"]
    assert (m["kind"], m["quantity"], m["balance_after"], m["unit_cost"]) == (
        "opening",
        "10.00",
        "10.00",
        "520.00",
    )

    res = _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "8"}])
    (m,) = res.json()["movements"]
    assert (m["kind"], m["quantity"], m["balance_after"]) == ("adjustment", "-2.00", "8.00")

    same = _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "8"}])
    assert same.json()["movements"] == []
    assert same.json()["unchanged_part_ids"] == [part["id"]]

    too_many = _adjust(owner_api, loc["id"], [{"part_id": part["id"], "change": "-9"}])
    assert too_many.status_code == 409
    assert "only 8.00 on hand" in too_many.json()["error"]["message"]

    detail = owner_api.get(f"/inventory/parts/{part['id']}").json()
    assert detail["stock"]["on_hand"] == "8.00"
    assert detail["levels"][0]["on_hand"] == "8.00"
    _ledger_matches(db)


def test_input_rules(owner_api: Api) -> None:
    part = _part(owner_api)
    loc = _main(owner_api)
    assert _adjust(owner_api, loc["id"], [{"part_id": part["id"]}]).status_code == 422
    assert (
        _adjust(
            owner_api, loc["id"], [{"part_id": part["id"], "counted": "1", "change": "1"}]
        ).status_code
        == 422
    )
    assert (
        _adjust(
            owner_api, loc["id"], [{"part_id": part["id"], "change": "1"}], reason=""
        ).status_code
        == 422
    )
    whole = _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "1.5"}])
    assert whole.status_code == 409
    assert "whole units" in whole.json()["error"]["message"]
    oil = _part(owner_api, sku="OIL-5W30", unit="litre")
    assert (
        _adjust(owner_api, loc["id"], [{"part_id": oil["id"], "counted": "12.5"}]).status_code
        == 201
    )
    dup = _adjust(
        owner_api,
        loc["id"],
        [{"part_id": oil["id"], "change": "1"}, {"part_id": oil["id"], "change": "1"}],
    )
    assert dup.status_code == 409
    assert (
        owner_api.post(
            "/inventory/adjustments",
            json={
                "location_id": loc["id"],
                "reason": "x" * 5,
                "lines": [{"part_id": oil["id"], "change": "1"}],
            },
        ).status_code
        == 422
    )  # Idempotency-Key required


def test_database_protects_the_ledger(owner_api: Api, db: Session) -> None:
    part = _part(owner_api)
    loc = _main(owner_api)
    _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "5"}])
    ids = {"loc": loc["id"], "part": part["id"]}
    for sql in (
        "UPDATE stock_levels SET on_hand = 99 WHERE location_id = :loc AND part_id = :part",
        "DELETE FROM stock_levels WHERE location_id = :loc AND part_id = :part",
        "UPDATE stock_movements SET quantity = 1 WHERE part_id = :part",
        "DELETE FROM stock_movements WHERE part_id = :part",
    ):
        with pytest.raises(DBAPIError):
            db.execute(text(sql), ids)
        db.rollback()
    # A movement that would make stock negative is rejected by the database itself.
    op = db.execute(
        text("SELECT id, created_by_user_id, organisation_id FROM stock_operations")
    ).first()
    db.add(
        StockMovement(
            organisation_id=op.organisation_id,
            branch_id=uuid.UUID(loc["branch"]["id"]),
            operation_id=op.id,
            location_id=uuid.UUID(loc["id"]),
            part_id=uuid.UUID(part["id"]),
            kind="adjustment",
            quantity=Decimal("-6"),
            unit_cost=Decimal("0"),
            created_by_user_id=op.created_by_user_id,
        )
    )
    with pytest.raises(DBAPIError):
        db.flush()
    db.rollback()
    _ledger_matches(db)


def test_adjustment_is_idempotent(owner_api: Api, db: Session) -> None:
    part = _part(owner_api)
    loc = _main(owner_api)
    key = "adj-" + uuid.uuid4().hex
    first = _adjust(owner_api, loc["id"], [{"part_id": part["id"], "change": "4"}], key=key)
    again = _adjust(owner_api, loc["id"], [{"part_id": part["id"], "change": "4"}], key=key)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["id"] == first.json()["id"]
    assert owner_api.get(f"/inventory/parts/{part['id']}").json()["stock"]["on_hand"] == "4.00"
    other = _adjust(owner_api, loc["id"], [{"part_id": part["id"], "change": "5"}], key=key)
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "idempotency_key_reused"


def test_concurrent_removals_cannot_oversell(
    owner_api: Api, org: OrgFixture, new_api: Any, db: Session
) -> None:
    part = _part(owner_api)
    loc = _main(owner_api)
    _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "3"}])
    apis = [new_api() for _ in range(5)]
    for a in apis:
        a.login(org.owner_email)
    results: list[int] = []

    def take(a: Api) -> None:
        results.append(_adjust(a, loc["id"], [{"part_id": part["id"], "change": "-1"}]).status_code)

    threads = [threading.Thread(target=take, args=(a,)) for a in apis]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 201, 201, 409, 409]
    with get_sessionmaker()() as s:
        assert s.scalar(select(func.sum(StockLevel.on_hand))) == Decimal("0.00")
        _ledger_matches(s)


# --------------------------------------------------------------------------- transfers


def test_transfer_moves_available_stock_only(owner_api: Api, org: OrgFixture, db: Session) -> None:
    part = _part(owner_api)
    src = _main(owner_api)
    van = owner_api.post(
        "/inventory/locations", json={"branch_id": str(org.branch_id), "name": "Service van"}
    ).json()
    _adjust(owner_api, src["id"], [{"part_id": part["id"], "counted": "5"}])
    # Reserve 2 for a job (reservations arrive in Phase 4b; set directly here).
    db.execute(
        update(StockLevel)
        .where(StockLevel.part_id == uuid.UUID(part["id"]))
        .values(reserved=Decimal("2"))
    )
    db.commit()

    over = _transfer(owner_api, src["id"], van["id"], [{"part_id": part["id"], "quantity": "4"}])
    assert over.status_code == 409
    assert "only 3.00 available" in over.json()["error"]["message"]
    below_reserved = _adjust(owner_api, src["id"], [{"part_id": part["id"], "counted": "1"}])
    assert below_reserved.status_code == 409
    assert "reserved" in below_reserved.json()["error"]["message"]

    ok = _transfer(owner_api, src["id"], van["id"], [{"part_id": part["id"], "quantity": "3"}])
    assert ok.status_code == 201, ok.text
    kinds = sorted((m["kind"], m["quantity"]) for m in ok.json()["movements"])
    assert kinds == [("transfer_in", "3.00"), ("transfer_out", "-3.00")]
    levels = {
        lv["location"]["name"]: lv
        for lv in owner_api.get(f"/inventory/parts/{part['id']}").json()["levels"]
    }
    assert (levels["Main store"]["on_hand"], levels["Main store"]["available"]) == ("2.00", "0.00")
    assert levels["Service van"]["on_hand"] == "3.00"
    assert (
        _transfer(
            owner_api, src["id"], src["id"], [{"part_id": part["id"], "quantity": "1"}]
        ).status_code
        == 409
    )
    _ledger_matches(db)


def test_archive_rules(owner_api: Api, org: OrgFixture) -> None:
    part = _part(owner_api)
    main = _main(owner_api)
    shelf = owner_api.post(
        "/inventory/locations", json={"branch_id": str(org.branch_id), "name": "Shelf B"}
    ).json()
    _adjust(owner_api, shelf["id"], [{"part_id": part["id"], "counted": "1"}])
    assert owner_api.post(f"/inventory/parts/{part['id']}/archive").status_code == 409
    assert owner_api.post(f"/inventory/locations/{shelf['id']}/archive").status_code == 409
    assert owner_api.post(f"/inventory/locations/{main['id']}/archive").status_code == 409
    _transfer(owner_api, shelf["id"], main["id"], [{"part_id": part["id"], "quantity": "1"}])
    assert owner_api.post(f"/inventory/locations/{shelf['id']}/archive").status_code == 200
    assert (
        _adjust(owner_api, shelf["id"], [{"part_id": part["id"], "change": "1"}]).status_code == 409
    )
    _adjust(owner_api, main["id"], [{"part_id": part["id"], "counted": "0"}])
    archived = owner_api.post(f"/inventory/parts/{part['id']}/archive")
    assert archived.status_code == 200
    assert owner_api.get("/inventory/parts").json()["total"] == 0
    assert (
        _adjust(owner_api, main["id"], [{"part_id": part["id"], "change": "1"}]).status_code == 409
    )


def test_low_stock(owner_api: Api) -> None:
    part = _part(owner_api)
    other = _part(owner_api, sku="OF-1")
    loc = _main(owner_api)
    _adjust(
        owner_api,
        loc["id"],
        [{"part_id": part["id"], "counted": "3"}, {"part_id": other["id"], "counted": "9"}],
    )
    res = owner_api.put(
        f"/inventory/parts/{part['id']}/levels/{loc['id']}", json={"min_quantity": "4"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["levels"][0]["is_low"] is True
    owner_api.put(f"/inventory/parts/{other['id']}/levels/{loc['id']}", json={"min_quantity": "2"})
    low = owner_api.get("/inventory/parts", params={"low_stock": True}).json()
    assert [p["sku"] for p in low["items"]] == ["BP-1234"]
    assert low["items"][0]["stock"]["low_locations"] == 1
    owner_api.put(f"/inventory/parts/{part['id']}/levels/{loc['id']}", json={"min_quantity": None})
    assert owner_api.get("/inventory/parts", params={"low_stock": True}).json()["total"] == 0


def test_movement_ledger_listing(owner_api: Api) -> None:
    part = _part(owner_api)
    loc = _main(owner_api)
    _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "2"}], reason="Opening count")
    _adjust(
        owner_api, loc["id"], [{"part_id": part["id"], "change": "-1"}], reason="Damaged in storage"
    )
    page = owner_api.get("/inventory/movements", params={"part_id": part["id"]}).json()
    assert page["total"] == 2
    assert [m["reason"] for m in page["items"]] == ["Damaged in storage", "Opening count"]
    assert page["items"][0]["created_by"] == "Olivia Owner"
    assert owner_api.get("/inventory/movements", params={"kind": "opening"}).json()["total"] == 1


# --------------------------------------------------------------------------- access


def test_permissions_and_scope(
    owner_api: Api, org: OrgFixture, new_api: Any, make_org: Any
) -> None:
    part = _part(owner_api)
    loc = _main(owner_api)
    _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "5"}])

    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    seen = mech.get(f"/inventory/parts/{part['id']}").json()
    assert seen["stock"]["on_hand"] == "5.00"
    assert seen["cost_price"] is None  # costs are hidden from mechanics
    assert mech.get("/inventory/movements").json()["items"][0]["unit_cost"] is None
    assert seen["levels"][0]["can_adjust"] is False
    assert _adjust(mech, loc["id"], [{"part_id": part["id"], "change": "1"}]).status_code == 403
    assert mech.post("/inventory/parts", json={"sku": "X1", "name": "X"}).status_code == 403

    # The catalogue is organisation-wide, so managing it needs an organisation-wide role.
    org.add_user("stores@example.com", [(org.role("inventory_manager"), None)])
    stores: Api = new_api()
    stores.login("stores@example.com")
    assert _adjust(stores, loc["id"], [{"part_id": part["id"], "change": "1"}]).status_code == 201
    assert stores.post("/inventory/parts", json={"sku": "X1", "name": "X"}).status_code == 201

    # A store person in another branch sees no stock from this branch and cannot touch it.
    north = org.add_branch("WHK2", "Windhoek North")
    org.add_user("north@example.com", [(org.role("inventory_manager"), north.id)])
    other_branch: Api = new_api()
    other_branch.login("north@example.com")
    view = other_branch.get(f"/inventory/parts/{part['id']}").json()
    assert view["stock"]["on_hand"] == "0.00"
    assert [lv["branch"]["name"] for lv in view["levels"]] == ["Windhoek North"]
    assert (
        _adjust(other_branch, loc["id"], [{"part_id": part["id"], "change": "-1"}]).status_code
        == 404
    )
    north_loc = _main(other_branch)
    assert (
        _transfer(
            other_branch, loc["id"], north_loc["id"], [{"part_id": part["id"], "quantity": "1"}]
        ).status_code
        == 404
    )

    org.add_user("acc@example.com", [(org.role("accounts"), org.branch_id)])
    acc: Api = new_api()
    acc.login("acc@example.com")
    assert acc.get("/inventory/parts").status_code == 200

    beta: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(beta.owner_email)
    assert b.get(f"/inventory/parts/{part['id']}").status_code == 404
    assert b.get("/inventory/parts").json()["total"] == 0
    assert b.get("/inventory/movements").json()["total"] == 0
    assert _adjust(b, loc["id"], [{"part_id": part["id"], "change": "1"}]).status_code == 404
    b_loc = _main(b)
    assert _adjust(b, b_loc["id"], [{"part_id": part["id"], "change": "1"}]).status_code == 404
