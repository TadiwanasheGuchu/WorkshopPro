import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import (
    AppSettings,
    CurrentPrincipal,
    DbSession,
    Mailer,
    Paging,
    RedisClient,
    client_ip,
)
from app.schemas.common import Page, Schema
from app.schemas.quotation import (
    DraftUpdate,
    PublicDecision,
    PublicQuotation,
    QuotationListItem,
    QuotationRead,
    ReviseRequest,
    SendRequest,
    SendResult,
    StaffDecision,
)
from app.services import quotations, rate_limit

router = APIRouter(tags=["quotations"])


@router.get("/quotations", response_model=Page[QuotationListItem], summary="List quotations")
def list_quotations(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    status: Literal["draft", "sent", "approved", "rejected", "expired"] | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[QuotationListItem]:
    items, total = quotations.list_quotations(db, principal, paging, status=status, search=search)
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/job-cards/{job_id}/quotation",
    response_model=QuotationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start the job's quotation",
    description="One quotation per job; further work is added as a new version.",
)
def create(job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> QuotationRead:
    return quotations.create_for_job(db, principal, job_id)


@router.get(
    "/job-cards/{job_id}/quotation",
    response_model=QuotationRead | None,
    summary="The job's quotation, if any",
)
def for_job(job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> QuotationRead | None:
    return quotations.for_job(db, principal, job_id)


@router.get("/quotations/{quotation_id}", response_model=QuotationRead, summary="Quotation")
def get(quotation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> QuotationRead:
    return quotations.get_quotation(db, principal, quotation_id)


@router.put(
    "/quotations/{quotation_id}/draft",
    response_model=QuotationRead,
    summary="Replace the draft's lines and details",
    description="Totals and tax are calculated by the server from the configured tax rates.",
)
def save_draft(
    quotation_id: uuid.UUID, body: DraftUpdate, principal: CurrentPrincipal, db: DbSession
) -> QuotationRead:
    return quotations.save_draft(db, principal, quotation_id, body)


@router.post(
    "/quotations/{quotation_id}/send",
    response_model=SendResult,
    summary="Send to the customer",
    description=(
        "Locks the version and creates a single-use customer link (returned once). "
        "Optionally emails the link to the customer's primary email."
    ),
)
def send(
    quotation_id: uuid.UUID,
    body: SendRequest,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    mailer: Mailer,
    background: BackgroundTasks,
) -> SendResult:
    result, email = quotations.send(db, principal, settings, quotation_id, body.email_customer)
    if email:
        background.add_task(mailer.send, email)
    return result


class LinkResponse(BaseModel):
    approval_url: str


@router.post(
    "/quotations/{quotation_id}/links",
    response_model=LinkResponse,
    summary="Create a new customer link",
    description="Revokes earlier links for this version.",
)
def new_link(
    quotation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession, settings: AppSettings
) -> LinkResponse:
    return LinkResponse(approval_url=quotations.new_link(db, principal, settings, quotation_id))


@router.post(
    "/quotations/{quotation_id}/revisions",
    response_model=QuotationRead,
    summary="Create a revision",
    description="Supersedes the current version. An earlier approval no longer applies.",
)
def revise(
    quotation_id: uuid.UUID, body: ReviseRequest, principal: CurrentPrincipal, db: DbSession
) -> QuotationRead:
    return quotations.revise(db, principal, quotation_id, body)


@router.post(
    "/quotations/{quotation_id}/decisions",
    response_model=QuotationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record the customer's decision",
    description="For approvals given in person, by phone or message. Evidence is required.",
)
def record_decision(
    quotation_id: uuid.UUID, body: StaffDecision, principal: CurrentPrincipal, db: DbSession
) -> QuotationRead:
    return quotations.record_decision(db, principal, quotation_id, body)


# --------------------------------------------------------------------------- public


class TokenBody(Schema):
    token: str = Field(min_length=20, max_length=100)


class PublicDecisionBody(PublicDecision):
    token: str = Field(min_length=20, max_length=100)


def _limit(request: Request, redis: RedisClient, settings: AppSettings, bucket: str) -> None:
    rate_limit.enforce(
        redis,
        bucket,
        client_ip(request) or "unknown",
        limit=60,
        window_seconds=900,
        enabled=settings.rate_limit_enabled,
    )


@router.post(
    "/public/quotations/view",
    response_model=PublicQuotation,
    summary="Customer: view a quotation by link token",
    description="No sign-in. Records that the link was opened; this is never an approval.",
)
def public_view(
    body: TokenBody, request: Request, db: DbSession, redis: RedisClient, settings: AppSettings
) -> PublicQuotation:
    _limit(request, redis, settings, "quote-view")
    return quotations.public_view(db, body.token)


@router.post(
    "/public/quotations/decision",
    response_model=PublicQuotation,
    summary="Customer: approve or decline",
    description=(
        "Single use. Records the exact version and total, the name given, time, IP address "
        "and browser."
    ),
)
def public_decide(
    body: PublicDecisionBody,
    request: Request,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
) -> PublicQuotation:
    _limit(request, redis, settings, "quote-decide")
    return quotations.public_decide(
        db, body.token, PublicDecision.model_validate(body.model_dump(exclude={"token"}))
    )
