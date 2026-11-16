import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.api.deps import AppSettings, CurrentPrincipal, DbSession, RedisClient, Storage, client_ip
from app.api.v1.quotations import TokenBody
from app.services import documents, rate_limit
from app.services.documents import Pdf

router = APIRouter(tags=["documents"])

PDF_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/pdf": {}}, "description": "PDF document"}
}


def _pdf(pdf: Pdf, download: bool) -> Response:
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{pdf.filename}"',
            # Documents contain customer and financial data: never cache in shared caches,
            # and always regenerate so balances are current.
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/quotations/{quotation_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Quotation PDF (current version)",
)
def quotation_pdf(
    quotation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession, download: bool = False
) -> Response:
    return _pdf(documents.quotation_pdf(db, principal, quotation_id), download)


@router.get(
    "/invoices/{invoice_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Invoice PDF",
    description="Drafts are clearly marked as not payable. Balances are as of now.",
)
def invoice_pdf(
    invoice_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession, download: bool = False
) -> Response:
    return _pdf(documents.invoice_pdf(db, principal, invoice_id), download)


@router.get(
    "/credit-notes/{credit_note_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Credit note PDF",
)
def credit_note_pdf(
    credit_note_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession, download: bool = False
) -> Response:
    return _pdf(documents.credit_note_pdf(db, principal, credit_note_id), download)


@router.get(
    "/payments/{payment_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Receipt PDF (payment, refund or reversal)",
)
def receipt_pdf(
    payment_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession, download: bool = False
) -> Response:
    return _pdf(documents.receipt_pdf(db, principal, payment_id), download)


@router.get(
    "/inspections/{inspection_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Inspection report PDF",
    description="Customer-readable report with results, notes, photo thumbnails and amendments.",
)
def inspection_pdf(
    inspection_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    storage: Storage,
    download: bool = False,
) -> Response:
    return _pdf(documents.inspection_pdf(db, principal, storage, inspection_id), download)


@router.post(
    "/public/quotations/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Customer: quotation PDF by link token",
    description="No sign-in. Same token rules as viewing; downloading is not approval.",
)
def public_quotation_pdf(
    body: TokenBody, request: Request, db: DbSession, redis: RedisClient, settings: AppSettings
) -> Response:
    rate_limit.enforce(
        redis,
        "quote-pdf",
        client_ip(request) or "unknown",
        limit=30,
        window_seconds=900,
        enabled=settings.rate_limit_enabled,
    )
    return _pdf(documents.public_quotation_pdf(db, body.token), download=True)
