"""Demo organisation for showing WorkshopPro (python -m app.cli seed-demo).

Everything is created through the real API in-process, so the same validation, workflow
rules, stock ledger, numbering and audit log apply as for staff using the app. All names
are marked as demo data. Never run this against a real workshop's database.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.time import utcnow
from app.models import Branch, Role, User, UserRoleAssignment
from app.services.organisations import create_organisation

ORG_NAME = "Demo Motors (demo data)"
DOMAIN = "demo-motors.example.com"
STAFF = [
    ("owner", "Owner (demo)", "owner"),
    ("manager", "Selma Workshop-Manager (demo)", "workshop_manager"),
    ("reception", "Tangeni Reception (demo)", "service_advisor"),
    ("mechanic", "Petrus Mechanic (demo)", "mechanic"),
    ("mechanic2", "Johannes Mechanic (demo)", "mechanic"),
    ("parts", "Martha Parts (demo)", "inventory_manager"),
    ("accounts", "Elina Accounts (demo)", "accounts"),
]


def staff_email(handle: str) -> str:
    return f"{handle}@{DOMAIN}"


class DemoError(RuntimeError):
    pass


class _Api:
    """Signed-in client that behaves like the browser (cookies + CSRF header)."""

    def __init__(self, app: Any, email: str, password: str) -> None:
        self.client = TestClient(app, base_url="https://demo.internal")
        self.call("POST", "/auth/login", json={"email": email, "password": password}, ok=204)

    def call(
        self, method: str, path: str, *, ok: int | tuple[int, ...] = (200, 201), **kw: Any
    ) -> Any:
        headers = kw.pop("headers", {}) or {}
        if method != "GET":
            token = (
                self.client.cookies.get("wp_csrf")
                or self.client.get("/api/v1/auth/csrf").json()["csrf_token"]
            )
            headers["X-CSRF-Token"] = token
        res = self.client.request(method, f"/api/v1{path}", headers=headers, **kw)
        expected = (ok,) if isinstance(ok, int) else ok
        if res.status_code not in expected:
            raise DemoError(f"{method} {path} -> {res.status_code}: {res.text[:300]}")
        return (
            res.json()
            if res.content and res.headers.get("content-type", "").startswith("application/json")
            else None
        )

    def get(self, path: str, **kw: Any) -> Any:
        return self.call("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.call("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self.call("PUT", path, **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self.call("PATCH", path, **kw)


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


@dataclass
class _Ctx:
    api: _Api
    mech: _Api
    branch: str
    vat: str
    location: str
    template: str
    users: dict[str, str]
    parts: dict[str, dict[str, Any]]


def _create_staff(db: Session, org_id: uuid.UUID, branch_id: uuid.UUID, password: str) -> None:
    roles = {
        r.template_key: r for r in db.scalars(select(Role).where(Role.organisation_id == org_id))
    }
    now = utcnow()
    for handle, name, role_key in STAFF[1:]:
        user = User(
            organisation_id=org_id,
            email=staff_email(handle),
            full_name=name,
            password_hash=hash_password(password),
            is_active=True,
            activated_at=now,
            invited_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            UserRoleAssignment(
                organisation_id=org_id,
                user_id=user.id,
                role_id=roles[role_key].id,
                branch_id=branch_id,
            )
        )
    db.commit()


def _move(api: _Api, job_id: str, to: str) -> None:
    job = api.get(f"/job-cards/{job_id}")
    api.post(f"/job-cards/{job_id}/transitions", json={"to_status": to, "version": job["version"]})


def _customer(
    c: _Ctx,
    first: str,
    last: str,
    phone: str,
    email: str | None,
    reg: str,
    make: str,
    model: str,
    year: int,
    **vehicle: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contacts = [{"kind": "phone", "value": phone, "is_primary": True}]
    if email:
        contacts.append({"kind": "email", "value": email, "is_primary": True})
    cust = c.api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "first_name": first,
            "last_name": last,
            "contacts": contacts,
            "preferred_contact_method": "email" if email else "phone",
            "notes": "Demo record.",
        },
    )
    if email:
        c.api.post(
            f"/customers/{cust['id']}/consents",
            json={
                "channel": "email",
                "status": "granted",
                "method": "verbal",
                "evidence": "Demo data: agreed at the counter",
            },
        )
    veh = c.api.post(
        "/vehicles",
        json={
            "customer_id": cust["id"],
            "registration_number": reg,
            "make": make,
            "model": model,
            "year": year,
            **vehicle,
        },
    )
    return cust, veh


def _job(
    c: _Ctx, cust: dict[str, Any], veh: dict[str, Any], complaint: str, **extra: Any
) -> dict[str, Any]:
    return c.api.post(
        "/job-cards",
        json={
            "branch_id": c.branch,
            "customer_id": cust["id"],
            "vehicle_id": veh["id"],
            "complaint": complaint,
            **extra,
        },
    )


def _inspect(c: _Ctx, job: dict[str, Any], kind: str, attention: dict[str, str]) -> None:
    ins = c.mech.post(
        f"/job-cards/{job['id']}/inspections", json={"template_id": c.template, "kind": kind}
    )
    for item in ins["items"]:
        label = item.get("label") or item.get("name") or ""
        note = next((n for k, n in attention.items() if k.lower() in label.lower()), None)
        body = {"result": "attention", "notes": note} if note else {"result": "pass"}
        c.mech.patch(f"/inspections/{ins['id']}/items/{item['id']}", json=body)
    c.mech.post(f"/inspections/{ins['id']}/submit")


def _quote(c: _Ctx, job: dict[str, Any], lines: list[tuple[str, str, str, str]]) -> dict[str, Any]:
    q = c.api.post(f"/job-cards/{job['id']}/quotation")
    items = [
        {
            "kind": kind,
            "description": desc,
            "quantity": qty,
            "unit_price": price,
            "tax_rate_id": c.vat,
        }
        for kind, desc, qty, price in lines
    ]
    c.api.put(
        f"/quotations/{q['id']}/draft", json={"items": items, "terms": "Payment on collection."}
    )
    return c.api.post(f"/quotations/{q['id']}/send", json={"email_customer": True})


def _approve(c: _Ctx, sent: dict[str, Any], name: str) -> None:
    c.api.post(
        f"/quotations/{sent['quotation']['id']}/decisions",
        json={
            "decision": "approved",
            "method": "phone",
            "customer_name": name,
            "evidence": "Demo data: approved by phone",
        },
    )


def _parts_to_job(c: _Ctx, job: dict[str, Any], sku: str, qty: str, issue: bool) -> None:
    line = {"location_id": c.location, "lines": [{"part_id": c.parts[sku]["id"], "quantity": qty}]}
    c.api.post(f"/job-cards/{job['id']}/parts/reservations", headers=_key(), json=line)
    if issue:
        c.api.post(f"/job-cards/{job['id']}/parts/issues", headers=_key(), json=line)


def seed(db: Session, app: Any, password: str) -> str:
    if db.scalar(select(User.id).where(User.email == staff_email("owner"))) is not None:
        raise DemoError("The demo organisation already exists.")
    result = create_organisation(
        db,
        name=ORG_NAME,
        owner_email=staff_email("owner"),
        owner_name="Owner (demo)",
        owner_password=password,
        branch_name="Windhoek (demo)",
        branch_code="WHK",
    )
    org_id = result.organisation.id
    branch_id = db.scalar(select(Branch.id).where(Branch.organisation_id == org_id))
    if branch_id is None:
        raise DemoError("The demo branch was not created.")
    _create_staff(db, org_id, branch_id, password)

    api = _Api(app, staff_email("owner"), password)
    mech = _Api(app, staff_email("mechanic"), password)
    users = {
        u["email"].split("@")[0]: u["id"]
        for u in api.get("/users", params={"page_size": 100})["items"]
    }
    vat = api.post(
        "/organisation/tax-rates",
        json={
            "name": "VAT 15% (demo: confirm rates with your tax adviser)",
            "rate_percent": "15",
            "is_default": True,
        },
    )["id"]
    api.post(f"/branches/{branch_id}/service-bays", json={"name": "Bay 1"})
    api.post(f"/branches/{branch_id}/service-bays", json={"name": "Bay 2"})
    location = next(loc for loc in api.get("/inventory/locations") if loc["is_default"])["id"]
    template = next(t["id"] for t in api.get("/inspection-templates") if t["is_default"])
    c = _Ctx(api, mech, str(branch_id), vat, location, template, users, {})

    # Parts, supplier and stock
    catalogue = [
        ("BP-FR-HLX", "Front brake pads, Hilux", "520.00", "890.00", "8"),
        ("OF-TOY-01", "Oil filter, Toyota", "65.00", "120.00", "20"),
        ("EO-5W30-5L", "Engine oil 5W-30, 5 L", "480.00", "760.00", "12"),
        ("AF-NAV-01", "Air filter, Navara", "140.00", "260.00", "3"),
        ("WB-22", "Wiper blade 22 inch", "75.00", "150.00", "10"),
        ("BAT-652", "Battery 652, 12 V", "1450.00", "2150.00", "2"),
    ]
    for sku, name, cost, price, qty in catalogue:
        part = api.post(
            "/inventory/parts",
            json={"sku": sku, "name": name, "cost_price": cost, "selling_price": price},
        )
        c.parts[sku] = part
        api.post(
            "/inventory/adjustments",
            headers=_key(),
            json={
                "location_id": location,
                "reason": "Opening stock (demo data)",
                "lines": [{"part_id": part["id"], "counted": qty}],
            },
        )
        api.put(f"/inventory/parts/{part['id']}/levels/{location}", json={"min_quantity": "4"})
    supplier = api.post(
        "/suppliers",
        json={
            "name": "Demo Auto Parts Supplier",
            "phone": "+264 61 000 000",
            "email": f"sales@{DOMAIN}",
            "payment_terms_days": 30,
        },
    )
    po = api.post(
        "/purchase-orders",
        json={
            "branch_id": c.branch,
            "supplier_id": supplier["id"],
            "lines": [
                {"part_id": c.parts["AF-NAV-01"]["id"], "quantity": "6", "unit_cost": "140.00"},
                {"part_id": c.parts["BAT-652"]["id"], "quantity": "4", "unit_cost": "1450.00"},
            ],
        },
    )
    po = api.post(f"/purchase-orders/{po['id']}/approve", json={"version": po["version"]})
    first_line = po["lines"][0]["id"]
    api.post(
        f"/purchase-orders/{po['id']}/receive",
        headers=_key(),
        json={
            "location_id": location,
            "supplier_invoice_reference": "DEMO-INV-1001",
            "lines": [{"po_line_id": first_line, "quantity": "6"}],
        },
    )

    now = utcnow()
    # 1. Collected and paid in full (history)
    cust, veh = _customer(
        c,
        "Ndapewa",
        "Shikongo (demo)",
        "+264 81 000 0101",
        f"ndapewa@{DOMAIN}",
        "N 1201 W",
        "Toyota",
        "Hilux",
        2019,
        odometer_km=148200,
    )
    j = _job(
        c,
        cust,
        veh,
        "Squealing from the front brakes",
        requested_work="Brake service",
        intake_odometer_km=148200,
        fuel_level="half",
    )
    api.post(f"/job-cards/{j['id']}/assignments", json={"user_id": users["mechanic"]})
    _move(api, j["id"], "diagnosis_in_progress")
    _approve(
        c,
        _quote(
            c,
            j,
            [
                ("labour", "Front brake service", "1.5", "450.00"),
                ("part", "Front brake pads, Hilux", "1", "890.00"),
            ],
        ),
        "Ndapewa Shikongo",
    )
    _parts_to_job(c, j, "BP-FR-HLX", "1", issue=True)
    for s in ("repair_in_progress", "quality_inspection"):
        _move(api, j["id"], s)
    inv = api.post(f"/job-cards/{j['id']}/invoices")
    inv = api.post(f"/invoices/{inv['id']}/issue")
    api.post(
        "/payments",
        headers=_key(),
        json={
            "branch_id": c.branch,
            "customer_id": cust["id"],
            "method": "eft",
            "amount": inv["total"],
            "reference": "DEMO EFT 2201",
            "allocations": [{"invoice_id": inv["id"], "amount": inv["total"]}],
        },
    )
    _move(api, j["id"], "ready_for_collection")
    job = api.get(f"/job-cards/{j['id']}")
    api.post(
        f"/job-cards/{j['id']}/transitions",
        json={
            "to_status": "completed",
            "version": job["version"],
            "collected_by_name": "Ndapewa Shikongo",
        },
    )

    # 2. Ready for collection, invoice part-paid
    cust, veh = _customer(
        c,
        "Hendrik",
        "van Wyk (demo)",
        "+264 81 000 0102",
        f"hendrik@{DOMAIN}",
        "N 3304 W",
        "Nissan",
        "Navara",
        2017,
    )
    j = _job(
        c,
        cust,
        veh,
        "Engine light on, rough idle",
        requested_work="Diagnose and repair",
        promised_at=(now + timedelta(hours=4)).isoformat(),
    )
    api.post(f"/job-cards/{j['id']}/assignments", json={"user_id": users["mechanic2"]})
    _move(api, j["id"], "diagnosis_in_progress")
    _approve(
        c,
        _quote(
            c,
            j,
            [
                ("labour", "Diagnose misfire, replace air filter", "2", "450.00"),
                ("part", "Air filter, Navara", "1", "260.00"),
            ],
        ),
        "Hendrik van Wyk",
    )
    _parts_to_job(c, j, "AF-NAV-01", "1", issue=True)
    for s in ("repair_in_progress", "quality_inspection"):
        _move(api, j["id"], s)
    inv = api.post(f"/job-cards/{j['id']}/invoices")
    inv = api.post(f"/invoices/{inv['id']}/issue")
    api.post(
        "/payments",
        headers=_key(),
        json={
            "branch_id": c.branch,
            "customer_id": cust["id"],
            "method": "cash",
            "amount": "500.00",
            "allocations": [{"invoice_id": inv["id"], "amount": "500.00"}],
        },
    )
    _move(api, j["id"], "ready_for_collection")

    # 3. Repair in progress, parts reserved
    cust, veh = _customer(
        c,
        "Kaarina",
        "Amukoto (demo)",
        "+264 81 000 0103",
        None,
        "N 5521 W",
        "Toyota",
        "Corolla",
        2015,
    )
    j = _job(
        c,
        cust,
        veh,
        "Due for major service",
        requested_work="Major service",
        promised_at=(now + timedelta(days=1)).isoformat(),
    )
    api.post(f"/job-cards/{j['id']}/assignments", json={"user_id": users["mechanic"]})
    _move(api, j["id"], "inspection_pending")
    _inspect(
        c,
        j,
        "intake",
        {"wiper": "Front wipers smearing; recommend replacement", "tyre": "Rear tyres at 3 mm"},
    )
    _move(api, j["id"], "diagnosis_in_progress")
    _approve(
        c,
        _quote(
            c,
            j,
            [
                ("labour", "Major service", "3", "450.00"),
                ("part", "Engine oil 5W-30, 5 L", "1", "760.00"),
                ("part", "Oil filter, Toyota", "1", "120.00"),
                ("part", "Wiper blade 22 inch", "2", "150.00"),
            ],
        ),
        "Kaarina Amukoto",
    )
    _parts_to_job(c, j, "EO-5W30-5L", "1", issue=True)
    _parts_to_job(c, j, "OF-TOY-01", "1", issue=False)
    _move(api, j["id"], "repair_in_progress")

    # 4. Awaiting the customer's approval (quotation link sent)
    cust, veh = _customer(
        c,
        "Simon",
        "Haufiku (demo)",
        "+264 81 000 0104",
        f"simon@{DOMAIN}",
        "N 7710 W",
        "Ford",
        "Ranger",
        2020,
    )
    j = _job(c, cust, veh, "Battery not holding charge", requested_work="Test and replace battery")
    api.post(f"/job-cards/{j['id']}/assignments", json={"user_id": users["mechanic2"]})
    _move(api, j["id"], "diagnosis_in_progress")
    _quote(
        c,
        j,
        [
            ("labour", "Battery and charging test", "0.5", "450.00"),
            ("part", "Battery 652, 12 V", "1", "2150.00"),
        ],
    )
    _move(api, j["id"], "awaiting_approval")

    # 5. Overdue, still in diagnosis
    cust, veh = _customer(
        c,
        "Lahja",
        "Nambahu (demo)",
        "+264 81 000 0105",
        f"lahja@{DOMAIN}",
        "N 9032 W",
        "Volkswagen",
        "Polo",
        2016,
    )
    j = _job(
        c,
        cust,
        veh,
        "Gearbox noise in 2nd gear",
        priority="high",
        promised_at=(now - timedelta(hours=6)).isoformat(),
    )
    api.post(f"/job-cards/{j['id']}/assignments", json={"user_id": users["mechanic"]})
    _move(api, j["id"], "diagnosis_in_progress")

    # 6. Just received
    cust, veh = _customer(
        c, "David", "Kandjii (demo)", "+264 81 000 0106", None, "N 4410 W", "Isuzu", "D-Max", 2021
    )
    _job(c, cust, veh, "Aircon blowing warm air", intake_odometer_km=61200, fuel_level="quarter")

    # Appointment tomorrow
    tomorrow = (now + timedelta(days=1)).date().isoformat()
    api.post(
        "/appointments",
        json={
            "branch_id": c.branch,
            "customer_id": cust["id"],
            "date": tomorrow,
            "start_time": "09:00",
            "duration_minutes": 90,
            "reason": "Follow-up: aircon re-gas (demo)",
        },
    )
    return ORG_NAME
