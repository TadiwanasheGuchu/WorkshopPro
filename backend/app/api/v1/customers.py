import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession, Paging
from app.schemas.common import Page
from app.schemas.customer import (
    ConsentInput,
    ConsentRead,
    CustomerCreate,
    CustomerDetail,
    CustomerSummary,
    CustomerUpdate,
)
from app.services import customers

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get(
    "",
    response_model=Page[CustomerSummary],
    summary="List customers",
    description=(
        "`search` matches name, contact person, any phone number (digits only are enough) "
        "or email, and the registration number of the customer's vehicles."
    ),
)
def list_customers(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    include_archived: bool = False,
) -> Page[CustomerSummary]:
    items, total = customers.list_customers(
        db, principal, paging, search=search, include_archived=include_archived
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "",
    response_model=CustomerDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Register a customer",
)
def create_customer(
    body: CustomerCreate, principal: CurrentPrincipal, db: DbSession
) -> CustomerDetail:
    return customers.create_customer(db, principal, body)


@router.get("/{customer_id}", response_model=CustomerDetail, summary="Customer details")
def get_customer(
    customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> CustomerDetail:
    return customers.get_customer(db, principal, customer_id)


@router.patch(
    "/{customer_id}",
    response_model=CustomerDetail,
    summary="Update a customer",
    description="`contacts` and `addresses`, when present, replace the existing lists.",
)
def update_customer(
    customer_id: uuid.UUID, body: CustomerUpdate, principal: CurrentPrincipal, db: DbSession
) -> CustomerDetail:
    return customers.update_customer(db, principal, customer_id, body)


@router.post(
    "/{customer_id}/archive",
    response_model=CustomerDetail,
    summary="Archive a customer",
    description="Only customers without active vehicles can be archived. History is kept.",
)
def archive_customer(
    customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> CustomerDetail:
    return customers.set_archived(db, principal, customer_id, True)


@router.post("/{customer_id}/restore", response_model=CustomerDetail, summary="Restore a customer")
def restore_customer(
    customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> CustomerDetail:
    return customers.set_archived(db, principal, customer_id, False)


@router.get(
    "/{customer_id}/consents",
    response_model=list[ConsentRead],
    summary="Consent history",
    description="Every consent record, newest first. The newest per channel is current.",
)
def consent_history(
    customer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[ConsentRead]:
    return customers.consent_history(db, principal, customer_id)


@router.post(
    "/{customer_id}/consents",
    response_model=ConsentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record communication consent",
    description="Consent records are never edited; record a new grant or withdrawal instead.",
)
def record_consent(
    customer_id: uuid.UUID, body: ConsentInput, principal: CurrentPrincipal, db: DbSession
) -> ConsentRead:
    return customers.record_consent(db, principal, customer_id, body)
