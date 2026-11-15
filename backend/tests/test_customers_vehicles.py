from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Role, RolePermission
from app.permissions.catalogue import P
from tests.conftest import Api, OrgFixture

INDIVIDUAL = {
    "customer_type": "individual",
    "first_name": "Ndapewa",
    "last_name": "Shikongo",
    "preferred_contact_method": "whatsapp",
    "contacts": [
        {"kind": "phone", "value": "081 234 5678", "label": "Mobile"},
        {"kind": "phone", "value": "+264 61 123 456", "label": "Work"},
        {"kind": "email", "value": "Ndapewa@Example.com"},
    ],
    "addresses": [{"kind": "physical", "line1": "12 Sam Nujoma Drive", "city": "Windhoek"}],
}


def _customer(api: Api, **overrides: Any) -> dict[str, Any]:
    res = api.post("/customers", json={**INDIVIDUAL, **overrides})
    assert res.status_code == 201, res.text
    return res.json()


def _vehicle(api: Api, customer_id: str, **overrides: Any) -> dict[str, Any]:
    body = {
        "customer_id": customer_id,
        "registration_number": "n 12345 w",
        "make": "Toyota",
        "model": "Hilux",
        "year": 2019,
        "odometer_km": 120500,
        **overrides,
    }
    res = api.post("/vehicles", json=body)
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- customers


def test_register_customer_normalises_contacts(owner_api: Api) -> None:
    c = _customer(owner_api)

    assert c["display_name"] == "Ndapewa Shikongo"
    phones = [x for x in c["contacts"] if x["kind"] == "phone"]
    assert [p["value"] for p in phones] == ["0812345678", "+26461123456"]
    assert [p["is_primary"] for p in phones] == [True, False]  # first becomes primary
    email = next(x for x in c["contacts"] if x["kind"] == "email")
    assert email["value"] == "ndapewa@example.com"
    assert c["addresses"][0]["city"] == "Windhoek"


@pytest.mark.parametrize(
    "body",
    [
        {"customer_type": "individual", "first_name": "No surname"},
        {"customer_type": "company"},
        {**INDIVIDUAL, "contacts": [{"kind": "phone", "value": "12"}]},
        {**INDIVIDUAL, "contacts": [{"kind": "email", "value": "not-an-email"}]},
        {
            **INDIVIDUAL,
            "contacts": [
                {"kind": "phone", "value": "0811111111", "is_primary": True},
                {"kind": "phone", "value": "0812222222", "is_primary": True},
            ],
        },
        {**INDIVIDUAL, "customer_type": "alien"},
    ],
)
def test_invalid_customers_rejected(owner_api: Api, body: dict[str, Any]) -> None:
    assert owner_api.post("/customers", json=body).status_code == 422


def test_company_customer(owner_api: Api) -> None:
    c = _customer(
        owner_api,
        customer_type="company",
        company_name="Namib Logistics (Pty) Ltd",
        contact_person="Fleet manager",
        first_name=None,
        last_name=None,
    )
    assert c["display_name"] == "Namib Logistics (Pty) Ltd"
    # Explicit nulls on optional text fields are accepted (regression: used to 500).
    res = owner_api.patch(f"/customers/{c['id']}", json={"contact_person": None, "notes": None})
    assert res.status_code == 200
    assert res.json()["contact_person"] is None


def test_customer_search_by_name_phone_email_and_registration(owner_api: Api) -> None:
    c = _customer(owner_api)
    _vehicle(owner_api, c["id"])
    _customer(owner_api, first_name="Other", last_name="Person", contacts=[])

    for term in ("shikongo", "0812345678", "234 5678", "ndapewa@example", "N12345W", "12345"):
        found = owner_api.get("/customers", params={"search": term}).json()
        assert [x["id"] for x in found["items"]] == [c["id"]], term

    listed = owner_api.get("/customers").json()
    assert listed["total"] == 2
    first = next(x for x in listed["items"] if x["id"] == c["id"])
    assert first["primary_phone"] == "0812345678"
    assert first["vehicle_count"] == 1


def test_update_replaces_contacts_and_is_audited(owner_api: Api, db: Session) -> None:
    c = _customer(owner_api)
    res = owner_api.patch(
        f"/customers/{c['id']}",
        json={
            "last_name": "Shikongo-Amutenya",
            "contacts": [{"kind": "phone", "value": "0819999999"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["display_name"] == "Ndapewa Shikongo-Amutenya"
    assert [x["value"] for x in body["contacts"]] == ["0819999999"]
    assert body["addresses"]  # untouched
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "customer.updated")).one()
    assert entry.changes["last_name"] == ["Shikongo", "Shikongo-Amutenya"]


def test_consent_is_append_only_with_current_state(owner_api: Api) -> None:
    c = _customer(owner_api)
    base = f"/customers/{c['id']}/consents"
    owner_api.post(
        base,
        json={
            "channel": "whatsapp",
            "status": "granted",
            "method": "signed_form",
            "evidence": "Intake form 231",
        },
    )
    owner_api.post(base, json={"channel": "whatsapp", "status": "withdrawn", "method": "verbal"})
    owner_api.post(base, json={"channel": "email", "status": "granted", "method": "written"})

    current = {x["channel"]: x for x in owner_api.get(f"/customers/{c['id']}").json()["consents"]}
    assert current["whatsapp"]["status"] == "withdrawn"
    assert current["email"]["status"] == "granted"
    assert current["whatsapp"]["recorded_by"] == "Olivia Owner"
    history = owner_api.get(base).json()
    assert [h["status"] for h in history if h["channel"] == "whatsapp"] == ["withdrawn", "granted"]
    assert (
        owner_api.post(
            base, json={"channel": "carrier-pigeon", "status": "granted", "method": "verbal"}
        ).status_code
        == 422
    )


def test_customer_with_active_vehicle_cannot_be_archived(owner_api: Api) -> None:
    c = _customer(owner_api)
    v = _vehicle(owner_api, c["id"])
    assert owner_api.post(f"/customers/{c['id']}/archive").status_code == 409

    owner_api.post(f"/vehicles/{v['id']}/archive")
    archived = owner_api.post(f"/customers/{c['id']}/archive").json()
    assert archived["archived_at"] is not None
    assert owner_api.get("/customers").json()["total"] == 0
    assert owner_api.get("/customers", params={"include_archived": True}).json()["total"] == 1
    # Archived customers cannot receive new vehicles.
    blocked = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 1 OK",
            "make": "VW",
            "model": "Polo",
        },
    )
    assert blocked.status_code == 409


# --------------------------------------------------------------------------- vehicles


def test_register_vehicle_normalises_identifiers(owner_api: Api) -> None:
    c = _customer(owner_api)
    v = _vehicle(owner_api, c["id"], vin="ahtfr22g 1234 56789")
    assert v["registration_number"] == "N 12345 W"
    assert v["vin"] == "AHTFR22G123456789"
    assert v["customer"]["display_name"] == "Ndapewa Shikongo"
    assert v["odometer_recorded_at"] is not None

    for term in ("n12345w", "N 12345", "hilux", "AHTFR22G"):
        assert owner_api.get("/vehicles", params={"search": term}).json()["total"] == 1, term


@pytest.mark.parametrize(
    "overrides",
    [
        {"registration_number": None, "vin": None},
        {"registration_number": "!!"},
        {"vin": "AHTFR22G12345678O"},  # 17 chars with O
        {"vin": "abc"},
        {"year": 1850},
        {"year": 2100},
        {"odometer_km": -5},
        {"fuel_type": "steam"},
    ],
)
def test_invalid_vehicles_rejected(owner_api: Api, overrides: dict[str, Any]) -> None:
    c = _customer(owner_api)
    body = {
        "customer_id": c["id"],
        "registration_number": "N 1 W",
        "make": "VW",
        "model": "Polo",
        **overrides,
    }
    assert owner_api.post("/vehicles", json=body).status_code == 422


def test_older_short_chassis_number_accepted_without_registration(owner_api: Api) -> None:
    c = _customer(owner_api)
    v = _vehicle(
        owner_api,
        c["id"],
        registration_number=None,
        vin="FJ40-12345",
        make="Toyota",
        model="Land Cruiser FJ40",
        year=1978,
    )
    assert v["vin"] == "FJ4012345"


def test_duplicate_registration_and_vin_conflict_but_archived_frees_them(owner_api: Api) -> None:
    c = _customer(owner_api)
    first = _vehicle(owner_api, c["id"], vin="AHTFR22G123456789")
    dup_reg = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N12345-W",
            "make": "VW",
            "model": "Polo",
        },
    )
    dup_vin = owner_api.post(
        "/vehicles",
        json={"customer_id": c["id"], "vin": "ahtfr22g123456789", "make": "VW", "model": "Polo"},
    )
    assert dup_reg.status_code == 409
    assert "registration" in dup_reg.json()["error"]["message"]
    assert dup_vin.status_code == 409
    assert "VIN" in dup_vin.json()["error"]["message"]

    owner_api.post(f"/vehicles/{first['id']}/archive")
    _vehicle(owner_api, c["id"])  # plate re-issued to another vehicle
    assert owner_api.post(f"/vehicles/{first['id']}/restore").status_code == 409


def test_odometer_cannot_go_down_without_reason(owner_api: Api, db: Session) -> None:
    c = _customer(owner_api)
    v = _vehicle(owner_api, c["id"])

    lower = owner_api.patch(f"/vehicles/{v['id']}", json={"odometer_km": 12050})
    assert lower.status_code == 422
    assert lower.json()["error"]["code"] == "odometer_decrease"

    fixed = owner_api.patch(
        f"/vehicles/{v['id']}",
        json={
            "odometer_km": 12050,
            "odometer_correction_reason": "Extra digit typed at registration",
        },
    )
    assert fixed.status_code == 200
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "vehicle.updated")).one()
    assert entry.changes["odometer_correction_reason"][1].startswith("Extra digit")
    assert owner_api.patch(f"/vehicles/{v['id']}", json={"odometer_km": 13000}).status_code == 200


def test_vehicle_transfer_keeps_ownership_history(owner_api: Api) -> None:
    seller = _customer(owner_api)
    buyer = _customer(owner_api, first_name="Johannes", last_name="Nghifitikeko", contacts=[])
    v = _vehicle(owner_api, seller["id"])

    moved = owner_api.post(
        f"/vehicles/{v['id']}/transfer", json={"customer_id": buyer["id"], "note": "Sold privately"}
    )
    assert moved.status_code == 200
    assert moved.json()["customer"]["id"] == buyer["id"]
    history = owner_api.get(f"/vehicles/{v['id']}/ownership").json()
    assert [h["customer"]["id"] for h in history] == [buyer["id"], seller["id"]]
    assert history[0]["ended_at"] is None
    assert history[1]["ended_at"] is not None
    assert (
        owner_api.post(
            f"/vehicles/{v['id']}/transfer", json={"customer_id": buyer["id"]}
        ).status_code
        == 409
    )


# --------------------------------------------------------------------------- access control


def test_cross_organisation_customers_and_vehicles_are_invisible(
    make_org: Any, new_api: Any
) -> None:
    org_a: OrgFixture = make_org("Alpha Auto")
    org_b: OrgFixture = make_org("Beta Panelbeaters")
    a: Api = new_api()
    a.login(org_a.owner_email)
    b: Api = new_api()
    b.login(org_b.owner_email)
    c = _customer(a)
    v = _vehicle(a, c["id"])

    assert b.get(f"/customers/{c['id']}").status_code == 404
    assert b.patch(f"/customers/{c['id']}", json={"notes": "x"}).status_code == 404
    assert (
        b.post(
            f"/customers/{c['id']}/consents",
            json={"channel": "email", "status": "granted", "method": "verbal"},
        ).status_code
        == 404
    )
    assert b.get(f"/vehicles/{v['id']}").status_code == 404
    assert b.post(f"/vehicles/{v['id']}/transfer", json={"customer_id": c["id"]}).status_code == 404
    assert b.get("/customers", params={"search": "Shikongo"}).json()["total"] == 0
    assert b.get("/vehicles", params={"search": "N12345W"}).json()["total"] == 0
    # B cannot attach a vehicle to A's customer, and may reuse the same plate in its own org.
    b_cust = _customer(b)
    foreign = b.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 9 W",
            "make": "VW",
            "model": "Polo",
        },
    )
    assert foreign.status_code == 404
    assert _vehicle(b, b_cust["id"])["registration_number"] == "N 12345 W"
    # B cannot transfer its vehicle to A's customer.
    b_vehicle = b.get("/vehicles").json()["items"][0]
    assert (
        b.post(f"/vehicles/{b_vehicle['id']}/transfer", json={"customer_id": c["id"]}).status_code
        == 404
    )


def test_mechanic_can_view_but_not_change(org: OrgFixture, owner_api: Api, new_api: Any) -> None:
    c = _customer(owner_api)
    v = _vehicle(owner_api, c["id"])
    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")

    assert mech.get(f"/customers/{c['id']}").status_code == 200
    assert mech.get(f"/vehicles/{v['id']}").status_code == 200
    assert mech.post("/customers", json=INDIVIDUAL).status_code == 403
    assert mech.patch(f"/vehicles/{v['id']}", json={"colour": "Red"}).status_code == 403
    assert (
        mech.post(
            f"/customers/{c['id']}/consents",
            json={"channel": "email", "status": "granted", "method": "verbal"},
        ).status_code
        == 403
    )


def test_branch_scoped_advisor_works_with_all_customers(
    org: OrgFixture, owner_api: Api, new_api: Any
) -> None:
    other = org.add_branch("SWK", "Swakopmund")
    c = _customer(owner_api)
    org.add_user("advisor@example.com", [(org.role("service_advisor"), other.id)])
    advisor: Api = new_api()
    advisor.login("advisor@example.com")
    assert advisor.get(f"/customers/{c['id']}").status_code == 200
    assert (
        advisor.patch(f"/customers/{c['id']}", json={"notes": "Prefers mornings"}).status_code
        == 200
    )


def test_user_without_customer_permissions_denied(
    org: OrgFixture, new_api: Any, db: Session
) -> None:
    role = Role(organisation_id=org.id, name="Stores only")
    db.add(role)
    db.flush()
    db.add(RolePermission(role_id=role.id, permission=P.BRANCHES_VIEW))
    db.commit()
    org.add_user("stores@example.com", [(role, None)])
    api: Api = new_api()
    api.login("stores@example.com")
    assert api.get("/customers").status_code == 403
    assert api.get("/vehicles").status_code == 403
