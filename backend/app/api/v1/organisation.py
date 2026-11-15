import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession
from app.models import DocumentSequence
from app.permissions.catalogue import P
from app.schemas.organisation import (
    DocumentSequenceRead,
    DocumentSequenceUpdate,
    OrganisationRead,
    OrganisationUpdate,
    SettingsRead,
    SettingsUpdate,
    TaxRateCreate,
    TaxRateRead,
    TaxRateUpdate,
)
from app.services import organisations
from app.services.numbering import DOCUMENT_TYPE_LABELS, DocumentType, format_number

router = APIRouter(prefix="/organisation", tags=["organisation"])


@router.get("", response_model=OrganisationRead, summary="Current organisation profile")
def get_organisation(principal: CurrentPrincipal, db: DbSession) -> OrganisationRead:
    principal.require(P.SETTINGS_VIEW)
    return OrganisationRead.model_validate(organisations.get_organisation(db, principal))


@router.patch("", response_model=OrganisationRead, summary="Update organisation profile")
def update_organisation(
    body: OrganisationUpdate, principal: CurrentPrincipal, db: DbSession
) -> OrganisationRead:
    return OrganisationRead.model_validate(organisations.update_organisation(db, principal, body))


@router.get("/settings", response_model=SettingsRead, summary="Organisation preferences")
def get_settings(principal: CurrentPrincipal, db: DbSession) -> SettingsRead:
    principal.require(P.SETTINGS_VIEW)
    return SettingsRead.model_validate(organisations.get_settings(db, principal))


@router.patch("/settings", response_model=SettingsRead, summary="Update organisation preferences")
def update_settings(
    body: SettingsUpdate, principal: CurrentPrincipal, db: DbSession
) -> SettingsRead:
    return SettingsRead.model_validate(organisations.update_settings(db, principal, body))


@router.get(
    "/tax-rates",
    response_model=list[TaxRateRead],
    summary="List tax rates",
    description="No tax rate is pre-configured. Confirm rates with a qualified tax adviser.",
)
def list_tax_rates(principal: CurrentPrincipal, db: DbSession) -> list[TaxRateRead]:
    return [TaxRateRead.model_validate(r) for r in organisations.list_tax_rates(db, principal)]


@router.post(
    "/tax-rates",
    response_model=TaxRateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tax rate",
)
def create_tax_rate(body: TaxRateCreate, principal: CurrentPrincipal, db: DbSession) -> TaxRateRead:
    return TaxRateRead.model_validate(organisations.create_tax_rate(db, principal, body))


@router.patch("/tax-rates/{tax_rate_id}", response_model=TaxRateRead, summary="Update a tax rate")
def update_tax_rate(
    tax_rate_id: uuid.UUID, body: TaxRateUpdate, principal: CurrentPrincipal, db: DbSession
) -> TaxRateRead:
    return TaxRateRead.model_validate(
        organisations.update_tax_rate(db, principal, tax_rate_id, body)
    )


def _sequence_read(seq: DocumentSequence) -> DocumentSequenceRead:
    doc_type = DocumentType(seq.document_type)
    return DocumentSequenceRead(
        document_type=doc_type,
        label=DOCUMENT_TYPE_LABELS[doc_type],
        prefix=seq.prefix,
        next_number=seq.next_number,
        padding=seq.padding,
        example=format_number(seq.prefix, seq.next_number, seq.padding),
        last_allocated_at=seq.last_allocated_at,
    )


@router.get(
    "/document-sequences",
    response_model=list[DocumentSequenceRead],
    summary="Document numbering",
)
def list_sequences(principal: CurrentPrincipal, db: DbSession) -> list[DocumentSequenceRead]:
    seqs = organisations.list_sequences(db, principal)
    order = list(DocumentType)
    return [
        _sequence_read(s)
        for s in sorted(seqs, key=lambda s: order.index(DocumentType(s.document_type)))
    ]


@router.patch(
    "/document-sequences/{document_type}",
    response_model=DocumentSequenceRead,
    summary="Update document numbering",
    description="The next number can be raised but never lowered, to avoid re-issuing numbers.",
)
def update_sequence(
    document_type: DocumentType,
    body: DocumentSequenceUpdate,
    principal: CurrentPrincipal,
    db: DbSession,
) -> DocumentSequenceRead:
    return _sequence_read(organisations.update_sequence(db, principal, document_type, body))
