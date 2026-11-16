"""PDF documents: content, draft marking, permissions, tenant scope, public link rules."""

# Fixtures are imported from test_invoices; pytest injects them by parameter name.
# ruff: noqa: F811

import io
import re
import uuid
from typing import Any

from PIL import Image
from pypdf import PdfReader
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import QuotationLink
from tests.conftest import Api, OrgFixture
from tests.test_invoices import _draft, _issued, _pay, job, vat  # noqa: F401
from tests.test_quotations import _quote, _send, _token


def _text(res: Any) -> str:
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["cache-control"] == "private, no-store"
    reader = PdfReader(io.BytesIO(res.content))
    text = re.sub(r"\s+", " ", " ".join(page.extract_text() for page in reader.pages))
    # Guard against Python objects being printed instead of rendered.
    assert "Paragraph(" not in text
    assert "frags" not in text
    return text


def _brand(api: Api) -> None:
    assert (
        api.patch(
            "/organisation",
            json={
                "tax_number": "VAT-123456",
                "address_line1": "12 Sam Nujoma Ave",
                "city": "Windhoek",
            },
        ).status_code
        == 200
    )
    assert (
        api.patch(
            "/organisation/settings", json={"document_footer": "Bank: FNB 62000000000"}
        ).status_code
        == 200
    )


def test_quotation_pdf(owner_api: Api, job: dict[str, Any]) -> None:
    _brand(owner_api)
    q = owner_api.get(f"/job-cards/{job['id']}/quotation").json()
    res = owner_api.get(f"/quotations/{q['id']}/pdf")
    text = _text(res)
    assert res.headers["content-disposition"].startswith('inline; filename="QT-000001-v1.pdf"')
    for expected in (
        "Quotation",
        "QT-000001",
        "Shikongo",
        "N 9 W",
        "Replace front pads",
        "BP-1234",
        "Tax: Standard (15%)",
        "N$ 1,742.25",
        "VAT-123456",
        "12 Sam Nujoma Ave",
        "Bank: FNB 62000000000",
        "Approved by Ndapewa Shikongo",
    ):
        assert expected in text, expected
    download = owner_api.get(f"/quotations/{q['id']}/pdf", params={"download": True})
    assert download.headers["content-disposition"].startswith("attachment;")


def test_invoice_pdf_draft_and_issued(
    owner_api: Api,
    job: dict[str, Any],
    org: OrgFixture,
) -> None:
    draft = _draft(owner_api, job)
    text = _text(owner_api.get(f"/invoices/{draft['id']}/pdf"))
    assert "this is not an invoice" in text
    owner_api.post(f"/invoices/{draft['id']}/issue")
    _pay(owner_api, org, job["customer_id"], "742.25", [(draft["id"], "742.25")])
    res = owner_api.get(f"/invoices/{draft['id']}/pdf")
    text = _text(res)
    assert 'filename="INV-000001.pdf"' in res.headers["content-disposition"]
    for expected in (
        "INV-000001",
        "Due date",
        "N$ 1,742.25",
        "RCT-000001",
        "Balance due",
        "N$ 1,000.00",
    ):
        assert expected in text, expected
    assert "not an invoice" not in text


def test_credit_note_and_receipt_pdfs(
    owner_api: Api,
    job: dict[str, Any],
    org: OrgFixture,
) -> None:
    inv = _issued(owner_api, job)
    credited = owner_api.post(
        f"/invoices/{inv['id']}/credit-notes",
        json={
            "reason": "Goodwill <b>discount</b> & thanks",
            "lines": [{"description": "Goodwill", "quantity": "1", "unit_price": "100"}],
        },
    ).json()
    cn = credited["credit_notes"][0]
    text = _text(owner_api.get(f"/credit-notes/{cn['id']}/pdf"))
    # User text is escaped, not interpreted as markup.
    for expected in (
        "Credit note",
        "CN-000001",
        "INV-000001",
        "N$ 100.00",
        "<b>discount</b> & thanks",
    ):
        assert expected in text, expected

    pay = _pay(owner_api, org, job["customer_id"], "2000.00", [(inv["id"], "1642.25")]).json()
    text = _text(owner_api.get(f"/payments/{pay['id']}/pdf"))
    for expected in (
        "Receipt",
        "RCT-000001",
        "N$ 2,000.00",
        "EFT / bank transfer",
        "N$ 357.75 is held as credit",
    ):
        assert expected in text, expected


def test_inspection_pdf_with_photo(owner_api: Api, job: dict[str, Any]) -> None:
    templates = owner_api.get("/inspection-templates").json()
    ins = owner_api.post(
        f"/job-cards/{job['id']}/inspections", json={"template_id": templates[0]["id"]}
    ).json()
    item = next(i for i in ins["items"] if i["label"] == "Front pads and discs")
    owner_api.patch(
        f"/inspections/{ins['id']}/items/{item['id']}",
        json={"result": "fail", "notes": "Pads at 2 mm"},
    )
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (40, 80, 120)).save(buf, "PNG")
    up = owner_api.post(
        f"/inspections/{ins['id']}/photos",
        files={"file": ("pads.png", buf.getvalue(), "image/png")},
        data={"item_id": item["id"]},
    )
    assert up.status_code == 201, up.text
    res = owner_api.get(f"/inspections/{ins['id']}/pdf")
    text = _text(res)
    for expected in (
        "Vehicle inspection",
        "Front pads and discs",
        "Failed",
        "Pads at 2 mm",
        "Draft",
    ):
        assert expected in text, expected
    reader = PdfReader(io.BytesIO(res.content))
    assert sum(len(page.images) for page in reader.pages) == 1


def test_pdf_access_follows_record_access(
    owner_api: Api,
    job: dict[str, Any],
    org: OrgFixture,
    make_org: Any,
    new_api: Any,
) -> None:
    inv = _issued(owner_api, job)
    q = owner_api.get(f"/job-cards/{job['id']}/quotation").json()
    pay = _pay(owner_api, org, job["customer_id"], "10.00").json()
    paths = [
        f"/invoices/{inv['id']}/pdf",
        f"/quotations/{q['id']}/pdf",
        f"/payments/{pay['id']}/pdf",
    ]

    other: OrgFixture = make_org("Beta")
    b: Api = new_api()
    b.login(other.owner_email)
    for path in paths:
        assert b.get(path).status_code == 404, path
    assert b.get(f"/credit-notes/{uuid.uuid4()}/pdf").status_code == 404

    org.add_user("mech@example.com", [(org.role("mechanic"), org.branch_id)])
    mech: Api = new_api()
    mech.login("mech@example.com")
    for path in paths:
        assert mech.get(path).status_code in (403, 404), path

    anonymous: Api = new_api()
    assert anonymous.get(paths[0]).status_code == 401


def test_public_quotation_pdf(
    owner_api: Api,
    org: OrgFixture,
    vat: str,
    new_api: Any,
    db: Session,
) -> None:
    c = owner_api.post(
        "/customers", json={"customer_type": "individual", "last_name": "Amutenya"}
    ).json()
    v = owner_api.post(
        "/vehicles",
        json={
            "customer_id": c["id"],
            "registration_number": "N 5 P",
            "make": "Ford",
            "model": "Ranger",
        },
    ).json()
    j = owner_api.post(
        "/job-cards",
        json={
            "branch_id": str(org.branch_id),
            "customer_id": c["id"],
            "vehicle_id": v["id"],
            "complaint": "Clutch",
        },
    ).json()
    owner_api.post(
        f"/job-cards/{j['id']}/transitions",
        json={"to_status": "diagnosis_in_progress", "version": 1},
    )
    sent = _send(owner_api, _quote(owner_api, j, vat))
    token = _token(sent["approval_url"])

    customer: Api = new_api()
    res = customer.post("/public/quotations/pdf", json={"token": token})
    text = _text(res)
    assert "QT-000001" in text
    assert "Amutenya" in text
    assert res.headers["content-disposition"].startswith("attachment;")
    # Downloading does not count as a view, and never as approval.
    view = customer.post("/public/quotations/view", json={"token": token}).json()
    assert view["status"] == "sent"

    assert customer.post("/public/quotations/pdf", json={"token": "x" * 43}).status_code == 404
    db.execute(update(QuotationLink).values(expires_at=utcnow()))
    db.commit()
    assert customer.post("/public/quotations/pdf", json={"token": token}).status_code == 404
