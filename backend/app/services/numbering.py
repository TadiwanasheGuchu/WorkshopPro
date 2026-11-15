"""Organisation-scoped document numbering (JC-000123, INV-000045, ...)."""

import uuid
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.time import utcnow
from app.models import DocumentSequence


class DocumentType(StrEnum):
    JOB_CARD = "job_card"
    QUOTATION = "quotation"
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    GOODS_RECEIVED = "goods_received"


DEFAULT_PREFIXES: dict[DocumentType, str] = {
    DocumentType.JOB_CARD: "JC",
    DocumentType.QUOTATION: "QT",
    DocumentType.INVOICE: "INV",
    DocumentType.CREDIT_NOTE: "CN",
    DocumentType.RECEIPT: "RCT",
    DocumentType.PURCHASE_ORDER: "PO",
    DocumentType.GOODS_RECEIVED: "GRN",
}

DOCUMENT_TYPE_LABELS: dict[DocumentType, str] = {
    DocumentType.JOB_CARD: "Job card",
    DocumentType.QUOTATION: "Quotation",
    DocumentType.INVOICE: "Invoice",
    DocumentType.CREDIT_NOTE: "Credit note",
    DocumentType.RECEIPT: "Receipt",
    DocumentType.PURCHASE_ORDER: "Purchase order",
    DocumentType.GOODS_RECEIVED: "Goods received note",
}


def format_number(prefix: str, number: int, padding: int) -> str:
    digits = str(number).zfill(padding)
    return f"{prefix}-{digits}" if prefix else digits


def seed_sequences(db: Session, organisation_id: uuid.UUID) -> None:
    for doc_type, prefix in DEFAULT_PREFIXES.items():
        db.add(
            DocumentSequence(
                organisation_id=organisation_id,
                document_type=doc_type.value,
                prefix=prefix,
                next_number=1,
                padding=6,
            )
        )


def allocate(db: Session, organisation_id: uuid.UUID, document_type: DocumentType) -> str:
    """Allocate the next number. Must run inside the transaction that creates the document;
    the row lock serialises concurrent allocations for the same organisation and type."""
    seq = db.scalar(
        select(DocumentSequence)
        .where(
            DocumentSequence.organisation_id == organisation_id,
            DocumentSequence.document_type == document_type.value,
        )
        .with_for_update()
    )
    if seq is None:
        raise NotFoundError(f"No numbering sequence configured for {document_type.value}.")
    number = format_number(seq.prefix, seq.next_number, seq.padding)
    seq.next_number += 1
    seq.last_allocated_at = utcnow()
    return number
