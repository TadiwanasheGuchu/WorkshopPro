import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentPrincipal, DbSession, Storage
from app.schemas.inspection import (
    AmendmentCreate,
    InspectionCreate,
    InspectionDetail,
    InspectionUpdate,
    ItemRead,
    ItemUpdate,
    PhotoRead,
    TemplateInput,
    TemplateRead,
)
from app.services import inspection_templates, inspections
from app.services.images import MAX_UPLOAD_BYTES, UploadTooLargeError

router = APIRouter(tags=["inspections"])


# --------------------------------------------------------------------------- templates


@router.get("/inspection-templates", response_model=list[TemplateRead], summary="List templates")
def list_templates(
    principal: CurrentPrincipal, db: DbSession, include_archived: bool = False
) -> list[TemplateRead]:
    return inspection_templates.list_templates(db, principal, include_archived=include_archived)


@router.post(
    "/inspection-templates",
    response_model=TemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a template",
)
def create_template(
    body: TemplateInput, principal: CurrentPrincipal, db: DbSession
) -> TemplateRead:
    return inspection_templates.save_template(db, principal, body)


@router.get(
    "/inspection-templates/{template_id}",
    response_model=TemplateRead,
    summary="Template with items",
)
def get_template(
    template_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> TemplateRead:
    return inspection_templates.get_template(db, principal, template_id)


@router.put(
    "/inspection-templates/{template_id}",
    response_model=TemplateRead,
    summary="Replace a template",
    description="Inspections already started keep their own copy of the checklist.",
)
def update_template(
    template_id: uuid.UUID, body: TemplateInput, principal: CurrentPrincipal, db: DbSession
) -> TemplateRead:
    return inspection_templates.save_template(db, principal, body, template_id)


@router.post(
    "/inspection-templates/{template_id}/archive", response_model=TemplateRead, summary="Archive"
)
def archive_template(
    template_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> TemplateRead:
    return inspection_templates.set_archived(db, principal, template_id, True)


@router.post(
    "/inspection-templates/{template_id}/restore", response_model=TemplateRead, summary="Restore"
)
def restore_template(
    template_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> TemplateRead:
    return inspection_templates.set_archived(db, principal, template_id, False)


# --------------------------------------------------------------------------- inspections


@router.post(
    "/job-cards/{job_id}/inspections",
    response_model=InspectionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Start an inspection",
    description="Copies the template's checklist into a new draft inspection.",
)
def start_inspection(
    job_id: uuid.UUID, body: InspectionCreate, principal: CurrentPrincipal, db: DbSession
) -> InspectionDetail:
    return inspections.start_inspection(db, principal, job_id, body)


@router.get(
    "/inspections/{inspection_id}",
    response_model=InspectionDetail,
    summary="Inspection details",
    description="Visible to anyone who can see the job card.",
)
def get_inspection(
    inspection_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> InspectionDetail:
    return inspections.get_inspection(db, principal, inspection_id)


@router.patch(
    "/inspections/{inspection_id}", response_model=InspectionDetail, summary="Update draft"
)
def update_inspection(
    inspection_id: uuid.UUID, body: InspectionUpdate, principal: CurrentPrincipal, db: DbSession
) -> InspectionDetail:
    return inspections.update_inspection(db, principal, inspection_id, body)


@router.patch(
    "/inspections/{inspection_id}/items/{item_id}",
    response_model=ItemRead,
    summary="Record an item result",
    description="Drafts only. Called on every tap so progress is not lost on weak connections.",
)
def update_item(
    inspection_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemUpdate,
    principal: CurrentPrincipal,
    db: DbSession,
) -> ItemRead:
    return inspections.update_item(db, principal, inspection_id, item_id, body)


@router.post(
    "/inspections/{inspection_id}/submit",
    response_model=InspectionDetail,
    summary="Submit the inspection",
    description=(
        "Items marked 'attention' or 'failed' need a note or a photo (422 "
        "`inspection_incomplete`). Submitted inspections can only be changed by amendment."
    ),
)
def submit(
    inspection_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> InspectionDetail:
    return inspections.submit(db, principal, inspection_id)


@router.post(
    "/inspections/{inspection_id}/amendments",
    response_model=InspectionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Amend a submitted inspection",
    description="Records the previous result and notes, the new values and the reason.",
)
def amend(
    inspection_id: uuid.UUID, body: AmendmentCreate, principal: CurrentPrincipal, db: DbSession
) -> InspectionDetail:
    return inspections.amend(db, principal, inspection_id, body)


@router.post(
    "/inspections/{inspection_id}/photos",
    response_model=PhotoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a photo",
    description=(
        f"JPEG, PNG or WebP up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. The image is checked "
        "by decoding it, rotated upright, stripped of metadata (including location) and resized."
    ),
)
async def upload_photo(
    inspection_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    storage: Storage,
    file: Annotated[UploadFile, File()],
    item_id: Annotated[uuid.UUID | None, Form()] = None,
    caption: Annotated[str | None, Form(max_length=300)] = None,
) -> PhotoRead:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError(f"Photos must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return await run_in_threadpool(
        inspections.add_photo,
        db,
        storage,
        principal,
        inspection_id,
        raw=raw,
        filename=file.filename,
        item_id=item_id,
        caption=(caption or "").strip() or None,
    )


@router.delete(
    "/inspections/{inspection_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a photo from a draft",
)
def delete_photo(
    inspection_id: uuid.UUID,
    photo_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: DbSession,
    storage: Storage,
) -> Response:
    inspections.delete_photo(db, storage, principal, inspection_id, photo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
