"""PDF documents. Every function loads its record through the same permission-checked
service the JSON API uses, so a PDF is never more visible than the record itself.

PDFs are generated synchronously in the request: ReportLab renders a typical document in
well under 100 ms and nothing is stored (see docs/decisions/0005-pdf-generation.md).
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.documents import commercial
from app.documents import inspection as inspection_doc
from app.documents.base import OrgInfo, Party
from app.documents.commercial import CreditNoteLine, VehicleInfo
from app.integrations.storage import ObjectStorage
from app.models import (
    Branch,
    CreditNote,
    CreditNoteItem,
    Customer,
    CustomerAddress,
    CustomerContact,
    InspectionPhoto,
    Invoice,
    JobCard,
    Organisation,
    OrganisationSettings,
    StoredFile,
    Supplier,
    Vehicle,
)
from app.permissions.principal import Principal
from app.schemas.quotation import QuotationRead
from app.services import inspections, invoices, payments, purchasing, quotations


@dataclass(frozen=True)
class Pdf:
    filename: str
    content: bytes


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "document"


def org_info(db: Session, organisation_id: uuid.UUID) -> OrgInfo:
    o = db.get_one(Organisation, organisation_id)
    s = db.get_one(OrganisationSettings, organisation_id)
    city = " ".join(x for x in (o.postal_code, o.city) if x)
    return OrgInfo(
        name=o.name,
        legal_name=o.legal_name,
        address=[x for x in (o.address_line1, o.address_line2, city) if x],
        contact=[" · ".join(x for x in (o.phone, o.email, o.website) if x)]
        if any((o.phone, o.email, o.website))
        else [],
        tax_number=o.tax_number,
        registration_number=o.registration_number,
        footer=s.document_footer,
        date_format=s.date_format,
        timezone=s.timezone,
    )


def customer_party(db: Session, customer_id: uuid.UUID) -> Party:
    c = db.get_one(Customer, customer_id)
    lines: list[str] = []
    if c.customer_type == "company" and c.contact_person:
        lines.append(f"Attention: {c.contact_person}")
    address = db.scalar(
        select(CustomerAddress)
        .where(CustomerAddress.customer_id == c.id)
        .order_by(CustomerAddress.kind == "physical", CustomerAddress.position)
        .limit(1)
    )
    if address:
        lines += [x for x in (address.line1, address.line2) if x]
        place = " ".join(x for x in (address.postal_code, address.city) if x)
        if place:
            lines.append(place)
    for kind in ("phone", "email"):
        value = db.scalar(
            select(CustomerContact.value)
            .where(CustomerContact.customer_id == c.id, CustomerContact.kind == kind)
            .order_by(CustomerContact.is_primary.desc(), CustomerContact.position)
            .limit(1)
        )
        if value:
            lines.append(value)
    if c.tax_number:
        lines.append(f"Tax number {c.tax_number}")
    return Party(name=c.display_name, lines=lines)


def _job_vehicle(db: Session, job_id: uuid.UUID | None) -> VehicleInfo | None:
    if not job_id:
        return None
    job = db.get_one(JobCard, job_id)
    v = db.get_one(Vehicle, job.vehicle_id)
    return VehicleInfo(
        registration=v.registration_number,
        make=v.make,
        model=v.model,
        year=v.year,
        vin=v.vin,
        odometer_km=job.intake_odometer_km,
    )


# --------------------------------------------------------------------------- documents


def quotation_pdf(db: Session, principal: Principal, quotation_id: uuid.UUID) -> Pdf:
    q = quotations.get_quotation(db, principal, quotation_id)
    return _quotation(db, principal.organisation_id, q)


def _quotation(db: Session, organisation_id: uuid.UUID, q: QuotationRead) -> Pdf:
    content = commercial.quotation(
        org_info(db, organisation_id), q, customer_party(db, q.customer.id)
    )
    return Pdf(f"{_safe(q.quote_number)}-v{q.current.version_number}.pdf", content)


def public_quotation_pdf(db: Session, token: str) -> Pdf:
    """For the customer's link. Validates the token exactly like viewing does (expiry,
    revocation), but does not record a view."""
    version = quotations.version_for_token(db, token)
    q = quotations.read_for_document(db, version)
    return _quotation(db, version.organisation_id, q)


def invoice_pdf(db: Session, principal: Principal, invoice_id: uuid.UUID) -> Pdf:
    inv = invoices.get_invoice(db, principal, invoice_id)
    content = commercial.invoice(
        org_info(db, principal.organisation_id),
        inv,
        customer_party(db, inv.customer.id),
        _job_vehicle(db, inv.job_card.id if inv.job_card else None),
    )
    return Pdf(f"{_safe(inv.invoice_number or 'draft-invoice')}.pdf", content)


def credit_note_pdf(db: Session, principal: Principal, credit_note_id: uuid.UUID) -> Pdf:
    cn = db.scalar(
        select(CreditNote).where(
            CreditNote.id == credit_note_id,
            CreditNote.organisation_id == principal.organisation_id,
        )
    )
    if cn is None:
        raise NotFoundError("Credit note not found.")
    inv: Invoice = invoices.load(db, principal, cn.invoice_id)  # permission + branch scope
    lines = [
        CreditNoteLine(
            description=i.description,
            quantity=i.quantity,
            unit_price=i.unit_price,
            tax_rate_name=i.tax_rate_name,
            tax_rate_percent=i.tax_rate_percent,
            line_subtotal=i.line_subtotal,
            line_tax=i.line_tax,
            line_total=i.line_total,
        )
        for i in db.scalars(
            select(CreditNoteItem)
            .where(CreditNoteItem.credit_note_id == cn.id)
            .order_by(CreditNoteItem.position)
        )
    ]
    content = commercial.credit_note(
        org_info(db, principal.organisation_id),
        number=cn.credit_note_number,
        issue_date=cn.issue_date,
        reason=cn.reason,
        invoice_number=inv.invoice_number or "",
        currency=cn.currency_code,
        prices_include_tax=inv.prices_include_tax,
        lines=lines,
        subtotal=cn.subtotal,
        tax_total=cn.tax_total,
        total=cn.total,
        customer=customer_party(db, inv.customer_id),
    )
    return Pdf(f"{_safe(cn.credit_note_number)}.pdf", content)


def receipt_pdf(db: Session, principal: Principal, payment_id: uuid.UUID) -> Pdf:
    pay = payments.get_payment(db, principal, payment_id)
    content = commercial.receipt(
        org_info(db, principal.organisation_id), pay, customer_party(db, pay.customer.id)
    )
    return Pdf(f"{_safe(pay.receipt_number)}.pdf", content)


def inspection_pdf(
    db: Session, principal: Principal, storage: ObjectStorage, inspection_id: uuid.UUID
) -> Pdf:
    ins = inspections.get_inspection(db, principal, inspection_id)
    # Only files attached to this inspection can be embedded.
    keys = dict(
        db.execute(
            select(StoredFile.id, StoredFile.thumbnail_key)
            .join(InspectionPhoto, InspectionPhoto.file_id == StoredFile.id)
            .where(InspectionPhoto.inspection_id == ins.id)
        ).all()
    )

    def load(file_id: uuid.UUID) -> bytes | None:
        key = keys.get(file_id)
        return storage.get(key) if key else None

    customer_id = db.scalar(
        select(JobCard.customer_id).where(JobCard.id == uuid.UUID(ins.job_card["id"]))
    )
    content = inspection_doc.inspection(
        org_info(db, principal.organisation_id),
        ins,
        customer_party(db, customer_id) if customer_id else Party(name=ins.customer_name),
        load,
    )
    return Pdf(f"inspection-{_safe(ins.job_card['job_number'])}.pdf", content)


def purchase_order_pdf(db: Session, principal: Principal, po_id: uuid.UUID) -> Pdf:
    po = purchasing.get_order(db, principal, po_id)
    s = db.get_one(Supplier, po.supplier.id)
    supplier = Party(
        name=s.name,
        lines=[
            x
            for x in (
                f"Attention: {s.contact_person}" if s.contact_person else None,
                *(s.address.splitlines() if s.address else []),
                s.phone,
                s.email,
            )
            if x
        ],
    )
    b = db.get_one(Branch, po.branch.id)
    place = " ".join(x for x in (b.postal_code, b.city) if x)
    deliver_to = [x for x in (b.name, b.address_line1, b.address_line2, place, b.phone) if x]
    content = commercial.purchase_order(
        org_info(db, principal.organisation_id), po, supplier, deliver_to, s.account_number
    )
    return Pdf(f"{_safe(po.po_number)}.pdf", content)
