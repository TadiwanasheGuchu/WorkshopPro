import uuid

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.api.deps import (
    AppSettings,
    CurrentPrincipal,
    DbSession,
    Mailer,
    PortalCustomer,
    RedisClient,
    Storage,
    client_ip,
)
from app.api.v1.documents import PDF_RESPONSE, _pdf
from app.core.config import Settings
from app.core.security import CSRF_COOKIE, PORTAL_SESSION_COOKIE
from app.schemas.portal import (
    ConsumeRequest,
    LinkRequest,
    PortalAccess,
    PortalDecision,
    PortalHome,
    PortalInvite,
    PortalInvoice,
    PortalJob,
    PortalJobDetail,
    PortalMe,
    PortalMeUpdate,
    PortalQuotation,
    PortalVehicle,
)
from app.services import documents, portal, rate_limit

router = APIRouter(prefix="/portal", tags=["customer portal"])
staff_router = APIRouter(tags=["customer portal"])


def _cookie(
    response: Response, settings: Settings, name: str, value: str, *, http_only: bool
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=portal.SESSION_DAYS * 24 * 3600,
        httponly=http_only,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


# --------------------------------------------------------------------------- auth


@router.post(
    "/auth/request-link",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Email a sign-in link",
    description="Always 202, whether or not an account exists. Rate limited.",
)
def request_link(
    body: LinkRequest,
    request: Request,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
    mailer: Mailer,
    background: BackgroundTasks,
) -> None:
    ip = client_ip(request) or "unknown"
    rate_limit.enforce(
        redis,
        "portal-link-ip",
        ip,
        limit=20,
        window_seconds=3600,
        enabled=settings.rate_limit_enabled,
    )
    rate_limit.enforce(
        redis,
        "portal-link-email",
        body.email,
        limit=5,
        window_seconds=3600,
        enabled=settings.rate_limit_enabled,
    )
    for message in portal.request_link(db, settings, body.email):
        background.add_task(mailer.send, message)


@router.post(
    "/auth/consume",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign in with an emailed link",
    description="Single use. Sets the `wp_portal_session` (HTTP-only) and `wp_csrf` cookies.",
)
def consume(
    body: ConsumeRequest,
    request: Request,
    response: Response,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
) -> None:
    rate_limit.enforce(
        redis,
        "portal-consume",
        client_ip(request) or "unknown",
        limit=30,
        window_seconds=900,
        enabled=settings.rate_limit_enabled,
    )
    session_token, csrf = portal.consume(db, body.token, request.cookies.get(CSRF_COOKIE))
    _cookie(response, settings, PORTAL_SESSION_COOKIE, session_token, http_only=True)
    _cookie(response, settings, CSRF_COOKIE, csrf, http_only=False)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def logout(who: PortalCustomer, response: Response, db: DbSession, settings: AppSettings) -> None:
    portal.logout(db, who)
    response.delete_cookie(
        PORTAL_SESSION_COOKIE,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


# --------------------------------------------------------------------------- customer


@router.get("/home", response_model=PortalHome, summary="Overview for the signed-in customer")
def home(who: PortalCustomer, db: DbSession) -> PortalHome:
    return portal.home(db, who)


@router.get("/me", response_model=PortalMe, summary="Contact details and consent")
def me(who: PortalCustomer, db: DbSession) -> PortalMe:
    return portal.me(db, who)


@router.patch(
    "/me",
    response_model=PortalMe,
    summary="Update phone, preferred contact method and consent",
    description="Consent changes are recorded as new consent records (method customer_portal).",
)
def update_me(body: PortalMeUpdate, who: PortalCustomer, db: DbSession) -> PortalMe:
    return portal.update_me(db, who, body)


@router.get("/vehicles", response_model=list[PortalVehicle], summary="My vehicles")
def vehicles(who: PortalCustomer, db: DbSession) -> list[PortalVehicle]:
    return portal.vehicles(db, who)


@router.get("/jobs", response_model=list[PortalJob], summary="My jobs and service history")
def jobs(who: PortalCustomer, db: DbSession) -> list[PortalJob]:
    return portal.jobs(db, who)


@router.get("/jobs/{job_id}", response_model=PortalJobDetail, summary="Job progress")
def job(job_id: uuid.UUID, who: PortalCustomer, db: DbSession) -> PortalJobDetail:
    return portal.job_detail(db, who, job_id)


@router.get("/quotations/{quotation_id}", response_model=PortalQuotation, summary="Quotation")
def quotation(quotation_id: uuid.UUID, who: PortalCustomer, db: DbSession) -> PortalQuotation:
    return portal.quotation(db, who, quotation_id)


@router.post(
    "/quotations/{quotation_id}/decision",
    response_model=PortalQuotation,
    summary="Approve or decline a quotation",
    description="Records the exact version and total, the signed-in account, time and IP.",
)
def decide(
    quotation_id: uuid.UUID, body: PortalDecision, who: PortalCustomer, db: DbSession
) -> PortalQuotation:
    return portal.decide(db, who, quotation_id, body)


@router.get("/invoices", response_model=list[PortalInvoice], summary="My invoices and receipts")
def invoices(who: PortalCustomer, db: DbSession) -> list[PortalInvoice]:
    return portal.invoice_list(db, who)


@router.get(
    "/quotations/{quotation_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Quotation PDF",
)
def quotation_pdf(quotation_id: uuid.UUID, who: PortalCustomer, db: DbSession) -> Response:
    return _pdf(documents.portal_quotation_pdf(db, who, quotation_id), False)


@router.get(
    "/invoices/{invoice_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Invoice PDF",
)
def invoice_pdf(invoice_id: uuid.UUID, who: PortalCustomer, db: DbSession) -> Response:
    return _pdf(documents.portal_invoice_pdf(db, who, invoice_id), False)


@router.get(
    "/receipts/{payment_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Receipt PDF",
)
def receipt_pdf(payment_id: uuid.UUID, who: PortalCustomer, db: DbSession) -> Response:
    return _pdf(documents.portal_receipt_pdf(db, who, payment_id), False)


@router.get(
    "/inspections/{inspection_id}/pdf",
    response_class=Response,
    responses=PDF_RESPONSE,
    summary="Inspection report PDF (submitted inspections only)",
)
def inspection_pdf(
    inspection_id: uuid.UUID, who: PortalCustomer, db: DbSession, storage: Storage
) -> Response:
    return _pdf(documents.portal_inspection_pdf(db, who, storage, inspection_id), False)


# --------------------------------------------------------------------------- staff


@staff_router.get(
    "/customers/{customer_id}/portal", response_model=PortalAccess, summary="Customer portal access"
)
def access(customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> PortalAccess:
    return portal.get_access(db, principal, customer_id)


@staff_router.post(
    "/customers/{customer_id}/portal/invite",
    response_model=PortalAccess,
    summary="Give portal access and email a sign-in link",
)
def invite(
    customer_id: uuid.UUID,
    body: PortalInvite,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
    mailer: Mailer,
    background: BackgroundTasks,
) -> PortalAccess:
    result, message = portal.invite(db, principal, settings, customer_id, body.email)
    background.add_task(mailer.send, message)
    return result


@staff_router.post(
    "/customers/{customer_id}/portal/disable",
    response_model=PortalAccess,
    summary="Remove portal access and sign the customer out",
)
def disable(customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> PortalAccess:
    return portal.disable(db, principal, customer_id)
