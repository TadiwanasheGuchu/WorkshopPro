import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, IdempotencyKey, Paging
from app.schemas.common import Page
from app.schemas.purchasing import (
    CloseRequest,
    PoCreate,
    PoDraftUpdate,
    PoListItem,
    PoRead,
    ReceiveRequest,
    ReceiveResult,
    SupplierCreate,
    SupplierListItem,
    SupplierPartInput,
    SupplierRead,
    SupplierReturnCreate,
    SupplierUpdate,
    VersionBody,
)
from app.services import purchasing

router = APIRouter(tags=["suppliers and purchasing"])


def _replayed(response: Response, created: bool) -> None:
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"


# --------------------------------------------------------------------------- suppliers


@router.get("/suppliers", response_model=Page[SupplierListItem], summary="Suppliers")
def list_suppliers(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    include_archived: bool = False,
) -> Page[SupplierListItem]:
    items, total = purchasing.list_suppliers(
        db, principal, paging, search=search, include_archived=include_archived
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/suppliers",
    response_model=SupplierRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a supplier",
)
def create_supplier(
    body: SupplierCreate, principal: CurrentPrincipal, db: DbSession
) -> SupplierRead:
    return purchasing.create_supplier(db, principal, body)


@router.get("/suppliers/{supplier_id}", response_model=SupplierRead, summary="Supplier")
def get_supplier(
    supplier_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> SupplierRead:
    return purchasing.get_supplier(db, principal, supplier_id)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierRead, summary="Edit a supplier")
def update_supplier(
    supplier_id: uuid.UUID, body: SupplierUpdate, principal: CurrentPrincipal, db: DbSession
) -> SupplierRead:
    return purchasing.update_supplier(db, principal, supplier_id, body)


@router.post(
    "/suppliers/{supplier_id}/archive",
    response_model=SupplierRead,
    summary="Archive a supplier with no open orders",
)
def archive_supplier(
    supplier_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> SupplierRead:
    return purchasing.set_supplier_archived(db, principal, supplier_id, True)


@router.post("/suppliers/{supplier_id}/restore", response_model=SupplierRead, summary="Restore")
def restore_supplier(
    supplier_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> SupplierRead:
    return purchasing.set_supplier_archived(db, principal, supplier_id, False)


@router.put(
    "/suppliers/{supplier_id}/parts/{part_id}",
    response_model=SupplierRead,
    summary="Set the supplier's code, price and lead time for a part",
)
def set_supplier_part(
    supplier_id: uuid.UUID,
    part_id: uuid.UUID,
    body: SupplierPartInput,
    principal: CurrentPrincipal,
    db: DbSession,
) -> SupplierRead:
    return purchasing.set_supplier_part(db, principal, supplier_id, part_id, body)


@router.delete(
    "/suppliers/{supplier_id}/parts/{part_id}",
    response_model=SupplierRead,
    summary="Remove a supplier part reference",
)
def remove_supplier_part(
    supplier_id: uuid.UUID, part_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> SupplierRead:
    return purchasing.remove_supplier_part(db, principal, supplier_id, part_id)


# --------------------------------------------------------------------------- orders


@router.get("/purchase-orders", response_model=Page[PoListItem], summary="Purchase orders")
def list_orders(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    status: Literal[
        "draft", "approved", "partially_received", "received", "closed", "cancelled", "open", "done"
    ]
    | None = None,
    supplier_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[PoListItem]:
    items, total = purchasing.list_orders(
        db, principal, paging, status=status, supplier_id=supplier_id, search=search
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.post(
    "/purchase-orders",
    response_model=PoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a purchase order",
    description="Line costs default to the supplier's last cost, else the part's cost price.",
)
def create_order(body: PoCreate, principal: CurrentPrincipal, db: DbSession) -> PoRead:
    return purchasing.create_order(db, principal, body)


@router.get("/purchase-orders/{po_id}", response_model=PoRead, summary="Purchase order")
def get_order(po_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> PoRead:
    return purchasing.get_order(db, principal, po_id)


@router.put("/purchase-orders/{po_id}/draft", response_model=PoRead, summary="Edit a draft")
def save_draft(
    po_id: uuid.UUID, body: PoDraftUpdate, principal: CurrentPrincipal, db: DbSession
) -> PoRead:
    return purchasing.save_draft(db, principal, po_id, body)


@router.post("/purchase-orders/{po_id}/approve", response_model=PoRead, summary="Approve")
def approve(
    po_id: uuid.UUID, body: VersionBody, principal: CurrentPrincipal, db: DbSession
) -> PoRead:
    return purchasing.approve(db, principal, po_id, body)


@router.post(
    "/purchase-orders/{po_id}/cancel",
    response_model=PoRead,
    summary="Cancel an order with nothing received",
)
def cancel(
    po_id: uuid.UUID, body: CloseRequest, principal: CurrentPrincipal, db: DbSession
) -> PoRead:
    return purchasing.cancel(db, principal, po_id, body)


@router.post(
    "/purchase-orders/{po_id}/close",
    response_model=PoRead,
    summary="Close a partly received order short",
)
def close(
    po_id: uuid.UUID, body: CloseRequest, principal: CurrentPrincipal, db: DbSession
) -> PoRead:
    return purchasing.close(db, principal, po_id, body)


@router.post(
    "/purchase-orders/{po_id}/receive",
    response_model=ReceiveResult,
    status_code=status.HTTP_201_CREATED,
    summary="Receive goods (goods received note)",
    description=(
        "Adds stock at a location in the order's branch. Partial deliveries are allowed; "
        "never more than is outstanding. Updates the part's cost price to the received cost. "
        "Requires an Idempotency-Key."
    ),
)
def receive(
    po_id: uuid.UUID,
    body: ReceiveRequest,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> ReceiveResult:
    result, created = purchasing.receive(db, principal, po_id, body, idempotency_key)
    _replayed(response, created)
    return result


@router.post(
    "/purchase-orders/{po_id}/returns",
    response_model=ReceiveResult,
    status_code=status.HTTP_201_CREATED,
    summary="Return received goods to the supplier",
    description="Up to what was received on each line, net of earlier returns. Requires an "
    "Idempotency-Key.",
)
def return_to_supplier(
    po_id: uuid.UUID,
    body: SupplierReturnCreate,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> ReceiveResult:
    result, created = purchasing.return_to_supplier(db, principal, po_id, body, idempotency_key)
    _replayed(response, created)
    return result
