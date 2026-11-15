import io
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.storage import InMemoryStorage
from app.models import AuditLog
from tests.conftest import Api, OrgFixture


def _png(size: tuple[int, int] = (3000, 2000), *, gps: bool = False) -> bytes:
    img = Image.new("RGB", size, (200, 30, 30))
    buf = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "S", 2: (22.0, 33.0, 0.0)}  # GPSInfo
        exif[0x0110] = "PhoneModel"
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def job(org: OrgFixture, owner_api: Api) -> dict[str, Any]:
    c = owner_api.post(
        "/customers", json={"customer_type": "individual", "last_name": "Shikongo"}
    ).json()
    v = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 1 W",
            "make": "Toyota",
            "model": "Hilux",
        },
    ).json()
    j = owner_api.post(
        "/job-cards",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": c["id"],
            "vehicle_id": v["id"],
            "complaint": "Service",
            "intake_odometer_km": 50000,
        },
    ).json()
    return j


def _template_id(api: Api) -> str:
    templates = api.get("/inspection-templates").json()
    return next(t["id"] for t in templates if t["is_default"])


def _start(api: Api, job: dict[str, Any], kind: str = "intake") -> dict[str, Any]:
    res = api.post(
        f"/job-cards/{job['id']}/inspections", json={"template_id": _template_id(api), "kind": kind}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _upload(
    api: Api, inspection_id: str, data: bytes, item_id: str | None = None, name: str = "photo.png"
) -> Any:
    form = {"item_id": item_id} if item_id else {}
    return api.post(
        f"/inspections/{inspection_id}/photos", files={"file": (name, data, "image/png")}, data=form
    )


# --------------------------------------------------------------------------- templates


def test_default_template_seeded_with_all_sections(owner_api: Api) -> None:
    templates = owner_api.get("/inspection-templates").json()
    assert len(templates) == 1
    detail = owner_api.get(f"/inspection-templates/{templates[0]['id']}").json()
    sections = {i["section"] for i in detail["items"]}
    assert {
        "Brakes",
        "Tyres and wheels",
        "Fluids",
        "Existing damage",
        "Lights and indicators",
    } <= sections
    assert detail["item_count"] == len(detail["items"]) > 40


def test_template_edits_do_not_change_started_inspections(
    owner_api: Api, job: dict[str, Any]
) -> None:
    inspection = _start(owner_api, job)
    original_count = len(inspection["items"])
    tid = _template_id(owner_api)
    res = owner_api.put(
        f"/inspection-templates/{tid}",
        json={
            "name": "Quick check",
            "is_default": True,
            "items": [{"section": "Tyres", "label": "Tread depth"}],
        },
    )
    assert res.status_code == 200
    again = owner_api.get(f"/inspections/{inspection['id']}").json()
    assert len(again["items"]) == original_count
    assert again["template_name"] == "Standard vehicle inspection"


def test_last_active_template_cannot_be_archived(owner_api: Api) -> None:
    tid = _template_id(owner_api)
    assert owner_api.post(f"/inspection-templates/{tid}/archive").status_code == 409
    second = owner_api.post(
        "/inspection-templates",
        json={
            "name": "Quality check",
            "items": [{"section": "Road test", "label": "Brakes on road test"}],
        },
    )
    assert second.status_code == 201
    assert owner_api.post(f"/inspection-templates/{tid}/archive").status_code == 200
    dup = owner_api.post(
        "/inspection-templates",
        json={"name": "Quality check", "items": [{"section": "A", "label": "B"}]},
    )
    assert dup.status_code == 409


# --------------------------------------------------------------------------- lifecycle


def test_inspection_lifecycle(owner_api: Api, job: dict[str, Any], db: Session) -> None:
    inspection = _start(owner_api, job)
    assert inspection["status"] == "draft"
    assert inspection["odometer_km"] == 50000
    assert inspection["counts"]["not_inspected"] == len(inspection["items"])
    items = {i["label"]: i for i in inspection["items"]}
    base = f"/inspections/{inspection['id']}/items"

    assert (
        owner_api.post(f"/inspections/{inspection['id']}/submit").json()["error"]["code"]
        == "inspection_incomplete"
    )
    owner_api.patch(f"{base}/{items['Front pads and discs']['id']}", json={"result": "fail"})
    owner_api.patch(f"{base}/{items['Front left tyre']['id']}", json={"result": "attention"})
    owner_api.patch(
        f"{base}/{items['Headlights (low and high beam)']['id']}", json={"result": "pass"}
    )
    assert (
        owner_api.patch(f"{base}/{items['Horn']['id']}", json={"result": "broken"}).status_code
        == 422
    )

    missing = owner_api.post(f"/inspections/{inspection['id']}/submit").json()["error"]
    assert missing["code"] == "inspection_incomplete"
    assert set(missing["details"]["items"]) == {"Front pads and discs", "Front left tyre"}

    owner_api.patch(
        f"{base}/{items['Front pads and discs']['id']}",
        json={"notes": "Pads at 1 mm, discs scored"},
    )
    photo = _upload(owner_api, inspection["id"], _png(), items["Front left tyre"]["id"])
    assert photo.status_code == 201, photo.text

    done = owner_api.post(f"/inspections/{inspection['id']}/submit").json()
    assert done["status"] == "submitted"
    assert done["submitted_by"] == "Olivia Owner"
    assert done["counts"] == {"pass": 1, "attention": 1, "fail": 1, "not_inspected": len(items) - 3}
    assert done["capabilities"] == {"edit": False, "amend": True}

    # Submitted inspections are locked.
    assert (
        owner_api.patch(f"{base}/{items['Horn']['id']}", json={"result": "pass"}).status_code == 409
    )
    assert _upload(owner_api, inspection["id"], _png()).status_code == 409

    job_detail = owner_api.get(f"/job-cards/{job['id']}").json()
    assert job_detail["inspections"][0]["status"] == "submitted"
    assert job_detail["inspections"][0]["counts"]["fail"] == 1
    assert db.scalar(
        select(AuditLog.summary).where(AuditLog.action == "inspection.submitted")
    ).endswith("1 failed, 1 need attention")


def test_amendment_records_old_value_and_reason(
    owner_api: Api, job: dict[str, Any], db: Session
) -> None:
    inspection = _start(owner_api, job)
    item = inspection["items"][0]
    owner_api.patch(f"/inspections/{inspection['id']}/items/{item['id']}", json={"result": "pass"})
    owner_api.post(f"/inspections/{inspection['id']}/submit")

    no_reason = owner_api.post(
        f"/inspections/{inspection['id']}/amendments",
        json={"item_id": item["id"], "result": "fail"},
    )
    assert no_reason.status_code == 422
    res = owner_api.post(
        f"/inspections/{inspection['id']}/amendments",
        json={
            "item_id": item["id"],
            "result": "attention",
            "notes": "Small dent on left door",
            "reason": "Missed during intake",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["amendments"][0]["old_result"] == "pass"
    assert body["amendments"][0]["new_result"] == "attention"
    assert body["amendments"][0]["reason"] == "Missed during intake"
    assert body["items"][0]["result"] == "attention"
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "inspection.amended"))


# --------------------------------------------------------------------------- photos


def test_photo_is_resized_reencoded_and_metadata_stripped(
    owner_api: Api, job: dict[str, Any], storage: InMemoryStorage
) -> None:
    inspection = _start(owner_api, job)
    res = _upload(owner_api, inspection["id"], _png((4000, 3000), gps=True), name="IMG_1234.jpg")
    assert res.status_code == 201, res.text
    photo = res.json()

    stored = [data for key, (data, _) in storage.objects.items() if not key.endswith("_thumb.jpg")]
    assert len(stored) == 1
    with Image.open(io.BytesIO(stored[0])) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 1920
        assert 0x8825 not in img.getexif()  # no GPS
        assert 0x0110 not in img.getexif()  # no camera model

    full = owner_api.get(f"/files/{photo['file_id']}")
    assert full.status_code == 200
    assert full.headers["content-type"] == "image/jpeg"
    assert "private" in full.headers["cache-control"]
    thumb = owner_api.get(f"/files/{photo['file_id']}", params={"variant": "thumb"})
    with Image.open(io.BytesIO(thumb.content)) as img:
        assert max(img.size) == 400

    assert (
        owner_api.delete(f"/inspections/{inspection['id']}/photos/{photo['id']}").status_code == 204
    )
    assert storage.objects == {}
    assert owner_api.get(f"/files/{photo['file_id']}").status_code == 404


@pytest.mark.parametrize(
    ("data", "name", "status"),
    [
        (b"#!/bin/sh\necho not an image", "evil.jpg", 422),
        (b"", "empty.png", 422),
        (b"GIF89a" + b"\x00" * 100, "anim.gif", 422),
    ],
)
def test_invalid_uploads_rejected(
    owner_api: Api, job: dict[str, Any], data: bytes, name: str, status: int
) -> None:
    inspection = _start(owner_api, job)
    res = _upload(owner_api, inspection["id"], data, name=name)
    assert res.status_code == status
    assert res.json()["error"]["code"] == "invalid_upload"


def test_oversized_upload_rejected(owner_api: Api, job: dict[str, Any]) -> None:
    inspection = _start(owner_api, job)
    res = _upload(owner_api, inspection["id"], b"\xff" * (12 * 1024 * 1024 + 10))
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "upload_too_large"


# --------------------------------------------------------------------------- access


def test_inspection_access_follows_job_visibility(
    org: OrgFixture, owner_api: Api, job: dict[str, Any], new_api: Any
) -> None:
    inspection = _start(owner_api, job)
    photo = _upload(owner_api, inspection["id"], _png()).json()
    mech_user = org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")

    assert mech.get(f"/inspections/{inspection['id']}").status_code == 404
    assert mech.get(f"/files/{photo['file_id']}").status_code == 404
    assert (
        mech.post(
            f"/job-cards/{job['id']}/inspections", json={"template_id": _template_id(owner_api)}
        ).status_code
        == 404
    )

    owner_api.post(f"/job-cards/{job['id']}/assignments", json={"user_id": str(mech_user.id)})
    detail = mech.get(f"/inspections/{inspection['id']}")
    assert detail.status_code == 200
    assert detail.json()["capabilities"]["edit"] is True
    assert mech.get(f"/files/{photo['file_id']}").status_code == 200
    item = detail.json()["items"][0]
    assert (
        mech.patch(
            f"/inspections/{inspection['id']}/items/{item['id']}", json={"result": "pass"}
        ).status_code
        == 200
    )
    mech.post(f"/inspections/{inspection['id']}/submit")
    amend = mech.post(
        f"/inspections/{inspection['id']}/amendments",
        json={"item_id": item["id"], "result": "fail", "reason": "Recheck"},
    )
    assert amend.status_code == 403
    assert (
        mech.put(
            f"/inspection-templates/{_template_id(owner_api)}",
            json={"name": "X", "items": [{"section": "A", "label": "B"}]},
        ).status_code
        == 403
    )


def test_cross_organisation_inspections_and_files_invisible(
    make_org: Any, new_api: Any, owner_api: Api, job: dict[str, Any]
) -> None:
    inspection = _start(owner_api, job)
    photo = _upload(owner_api, inspection["id"], _png()).json()
    other: OrgFixture = make_org("Beta Panelbeaters")
    b: Api = new_api()
    b.login(other.owner_email)

    assert b.get(f"/inspections/{inspection['id']}").status_code == 404
    assert b.get(f"/files/{photo['file_id']}").status_code == 404
    assert (
        b.patch(
            f"/inspections/{inspection['id']}/items/{inspection['items'][0]['id']}",
            json={"result": "pass"},
        ).status_code
        == 404
    )
    assert _upload(b, inspection["id"], _png()).status_code == 404
    assert (
        b.post(
            f"/job-cards/{job['id']}/inspections", json={"template_id": _template_id(b)}
        ).status_code
        == 404
    )
    # B cannot start an inspection with A's template on its own job either.
    assert b.get(f"/inspection-templates/{_template_id(owner_api)}").status_code == 404
