"""Vehicle inspections on job cards.

Access follows job card visibility (app.services.job_cards): if you can see the job, you
can see its inspections. Recording results needs inspections.perform at the job's branch;
correcting a submitted inspection needs inspections.amend and is recorded as an amendment.
"""

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.time import utcnow
from app.integrations.storage import ObjectStorage
from app.models import (
    Branch,
    Customer,
    Inspection,
    InspectionAmendment,
    InspectionItem,
    InspectionPhoto,
    InspectionTemplate,
    InspectionTemplateItem,
    JobCard,
    Organisation,
    StoredFile,
    User,
    Vehicle,
)
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.inspection import (
    AmendmentCreate,
    AmendmentRead,
    InspectionCapabilities,
    InspectionCreate,
    InspectionDetail,
    InspectionUpdate,
    ItemRead,
    ItemUpdate,
    PhotoRead,
)
from app.services import audit
from app.services.common import get_scoped
from app.services.images import process_photo
from app.services.inspection_summary import counts as _counts
from app.services.job_cards import get_visible_job_card as get_visible_job
from app.services.job_workflow import TERMINAL, JobStatus

MAX_PHOTOS_PER_INSPECTION = 100
RESULTS = ("pass", "attention", "fail", "not_inspected")


class IncompleteInspectionError(AppError):
    status_code = 422
    code = "inspection_incomplete"


def _load(
    db: Session, principal: Principal, inspection_id: uuid.UUID
) -> tuple[Inspection, JobCard]:
    inspection = db.scalar(
        select(Inspection).where(
            Inspection.id == inspection_id, Inspection.organisation_id == principal.organisation_id
        )
    )
    if inspection is None:
        raise NotFoundError("Inspection not found.")
    try:
        job = get_visible_job(db, principal, inspection.job_card_id)
    except (NotFoundError, PermissionDeniedError) as exc:
        raise NotFoundError("Inspection not found.") from exc
    return inspection, job


def _require_editable(principal: Principal, inspection: Inspection) -> None:
    principal.require(P.INSPECTIONS_PERFORM, inspection.branch_id)
    if inspection.status != "draft":
        raise ConflictError("This inspection has been submitted. Use an amendment to correct it.")


def _names(db: Session, ids: list[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(wanted))).all())


def get_inspection(db: Session, principal: Principal, inspection_id: uuid.UUID) -> InspectionDetail:
    inspection, job = _load(db, principal, inspection_id)
    return read_detail(db, principal, inspection, job)


def read_detail(
    db: Session, principal: Principal, inspection: Inspection, job: JobCard
) -> InspectionDetail:
    """Build the detail for an inspection the caller is already allowed to see."""
    items = list(
        db.scalars(
            select(InspectionItem)
            .where(InspectionItem.inspection_id == inspection.id)
            .order_by(InspectionItem.position)
        )
    )
    photos = list(
        db.scalars(
            select(InspectionPhoto)
            .where(InspectionPhoto.inspection_id == inspection.id)
            .order_by(InspectionPhoto.created_at)
        )
    )
    amendments = list(
        db.scalars(
            select(InspectionAmendment)
            .where(InspectionAmendment.inspection_id == inspection.id)
            .order_by(InspectionAmendment.amended_at)
        )
    )
    names = _names(
        db,
        [inspection.started_by_user_id, inspection.submitted_by_user_id]
        + [a.amended_by_user_id for a in amendments],
    )
    by_item: dict[uuid.UUID | None, list[PhotoRead]] = defaultdict(list)
    for p in photos:
        by_item[p.item_id].append(
            PhotoRead(
                id=p.id,
                file_id=p.file_id,
                item_id=p.item_id,
                caption=p.caption,
                created_at=p.created_at,
            )
        )
    labels = {i.id: i.label for i in items}
    vehicle = db.get_one(Vehicle, inspection.vehicle_id)
    customer_name = db.scalar(select(Customer.display_name).where(Customer.id == job.customer_id))
    branch_name = db.scalar(select(Branch.name).where(Branch.id == inspection.branch_id))
    org_name = db.scalar(
        select(Organisation.name).where(Organisation.id == inspection.organisation_id)
    )
    editable = inspection.status == "draft" and principal.can(
        P.INSPECTIONS_PERFORM, inspection.branch_id
    )

    return InspectionDetail(
        id=inspection.id,
        kind=inspection.kind,  # type: ignore[arg-type]
        status=inspection.status,  # type: ignore[arg-type]
        template_name=inspection.template_name,
        started_by=names.get(inspection.started_by_user_id)
        if inspection.started_by_user_id
        else None,
        submitted_at=inspection.submitted_at,
        counts=_counts([i.result for i in items]),  # type: ignore[arg-type]
        job_card={"id": str(job.id), "job_number": job.job_number},
        vehicle={
            "id": str(vehicle.id),
            "registration_number": vehicle.registration_number,
            "vin": vehicle.vin,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
        },
        customer_name=customer_name or "",
        branch_name=branch_name or "",
        organisation_name=org_name or "",
        odometer_km=inspection.odometer_km,
        summary=inspection.summary,
        submitted_by=names.get(inspection.submitted_by_user_id)
        if inspection.submitted_by_user_id
        else None,
        created_at=inspection.created_at,
        items=[
            ItemRead(
                id=i.id,
                section=i.section,
                label=i.label,
                guidance=i.guidance,
                result=i.result,  # type: ignore[arg-type]
                notes=i.notes,
                photos=by_item.get(i.id, []),
            )
            for i in items
        ],
        general_photos=by_item.get(None, []),
        amendments=[
            AmendmentRead(
                item_label=labels.get(a.item_id, ""),
                old_result=a.old_result,  # type: ignore[arg-type]
                new_result=a.new_result,  # type: ignore[arg-type]
                old_notes=a.old_notes,
                new_notes=a.new_notes,
                reason=a.reason,
                amended_by=names.get(a.amended_by_user_id, ""),
                amended_at=a.amended_at,
            )
            for a in amendments
        ],
        capabilities=InspectionCapabilities(
            edit=editable,
            amend=inspection.status == "submitted"
            and principal.can(P.INSPECTIONS_AMEND, inspection.branch_id),
        ),
    )


def start_inspection(
    db: Session, principal: Principal, job_id: uuid.UUID, body: InspectionCreate
) -> InspectionDetail:
    job = get_visible_job(db, principal, job_id)
    principal.require(P.INSPECTIONS_PERFORM, job.branch_id)
    if JobStatus(job.status) in TERMINAL:
        raise ConflictError("This job is closed.")
    template = get_scoped(db, InspectionTemplate, body.template_id, principal.organisation_id)
    if template.archived_at is not None:
        raise ConflictError("This template is archived.")
    template_items = list(
        db.scalars(
            select(InspectionTemplateItem)
            .where(InspectionTemplateItem.template_id == template.id)
            .order_by(InspectionTemplateItem.position)
        )
    )
    inspection = Inspection(
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        job_card_id=job.id,
        vehicle_id=job.vehicle_id,
        template_id=template.id,
        template_name=template.name,
        kind=body.kind,
        status="draft",
        odometer_km=job.intake_odometer_km if body.kind == "intake" else None,
        started_by_user_id=principal.user_id,
    )
    db.add(inspection)
    db.flush()
    db.add_all(
        InspectionItem(
            inspection_id=inspection.id,
            section=t.section,
            label=t.label,
            guidance=t.guidance,
            position=t.position,
        )
        for t in template_items
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=job.branch_id,
        actor=principal,
        action="inspection.started",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"{body.kind.capitalize()} inspection started on job {job.job_number}",
        changes={"inspection_id": inspection.id, "template": template.name},
    )
    db.commit()
    return get_inspection(db, principal, inspection.id)


def update_inspection(
    db: Session, principal: Principal, inspection_id: uuid.UUID, body: InspectionUpdate
) -> InspectionDetail:
    inspection, _ = _load(db, principal, inspection_id)
    _require_editable(principal, inspection)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(inspection, key, value)
    db.commit()
    return get_inspection(db, principal, inspection.id)


def update_item(
    db: Session,
    principal: Principal,
    inspection_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemUpdate,
) -> ItemRead:
    """Autosaved from the checklist on every tap; last write wins per item."""
    inspection, _ = _load(db, principal, inspection_id)
    _require_editable(principal, inspection)
    item = db.scalar(
        select(InspectionItem).where(
            InspectionItem.id == item_id, InspectionItem.inspection_id == inspection.id
        )
    )
    if item is None:
        raise NotFoundError("Checklist item not found.")
    data = body.model_dump(exclude_unset=True)
    if "result" in data and data["result"] is not None:
        item.result = data["result"]
    if "notes" in data:
        item.notes = data["notes"]
    item.updated_at = utcnow()
    item.updated_by_user_id = principal.user_id
    db.commit()
    photos = db.scalars(
        select(InspectionPhoto)
        .where(InspectionPhoto.item_id == item.id)
        .order_by(InspectionPhoto.created_at)
    )
    return ItemRead(
        id=item.id,
        section=item.section,
        label=item.label,
        guidance=item.guidance,
        result=item.result,  # type: ignore[arg-type]
        notes=item.notes,
        photos=[
            PhotoRead(
                id=p.id,
                file_id=p.file_id,
                item_id=p.item_id,
                caption=p.caption,
                created_at=p.created_at,
            )
            for p in photos
        ],
    )


def submit(db: Session, principal: Principal, inspection_id: uuid.UUID) -> InspectionDetail:
    inspection, job = _load(db, principal, inspection_id)
    _require_editable(principal, inspection)
    items = list(
        db.scalars(select(InspectionItem).where(InspectionItem.inspection_id == inspection.id))
    )
    with_photos = set(
        db.scalars(
            select(InspectionPhoto.item_id).where(
                InspectionPhoto.inspection_id == inspection.id, InspectionPhoto.item_id.is_not(None)
            )
        )
    )
    unexplained = [
        i.label
        for i in items
        if i.result in ("attention", "fail")
        and not (i.notes or "").strip()
        and i.id not in with_photos
    ]
    if unexplained:
        raise IncompleteInspectionError(
            "Add a note or photo to every item marked 'attention' or 'failed'.",
            details={"items": unexplained},
        )
    if all(i.result == "not_inspected" for i in items):
        raise IncompleteInspectionError("Record at least one result before submitting.")
    inspection.status = "submitted"
    inspection.submitted_at = utcnow()
    inspection.submitted_by_user_id = principal.user_id
    counts = _counts([i.result for i in items])
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=inspection.branch_id,
        actor=principal,
        action="inspection.submitted",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"{inspection.kind.capitalize()} inspection submitted on job {job.job_number}: "
        f"{counts['fail']} failed, {counts['attention']} need attention",
        changes={"inspection_id": inspection.id, **counts},
    )
    db.commit()
    return get_inspection(db, principal, inspection.id)


def amend(
    db: Session, principal: Principal, inspection_id: uuid.UUID, body: AmendmentCreate
) -> InspectionDetail:
    inspection, job = _load(db, principal, inspection_id)
    principal.require(P.INSPECTIONS_AMEND, inspection.branch_id)
    if inspection.status != "submitted":
        raise ConflictError("Draft inspections can be edited directly.")
    item = db.scalar(
        select(InspectionItem)
        .where(InspectionItem.id == body.item_id, InspectionItem.inspection_id == inspection.id)
        .with_for_update()
    )
    if item is None:
        raise NotFoundError("Checklist item not found.")
    if item.result == body.result and (item.notes or None) == body.notes:
        raise ConflictError("Nothing to change.")
    db.add(
        InspectionAmendment(
            inspection_id=inspection.id,
            item_id=item.id,
            old_result=item.result,
            new_result=body.result,
            old_notes=item.notes,
            new_notes=body.notes,
            reason=body.reason,
            amended_by_user_id=principal.user_id,
        )
    )
    old = item.result
    item.result, item.notes = body.result, body.notes
    item.updated_at, item.updated_by_user_id = utcnow(), principal.user_id
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=inspection.branch_id,
        actor=principal,
        action="inspection.amended",
        entity_type="job_card",
        entity_id=job.id,
        summary=f"Inspection item '{item.label}' amended on job {job.job_number}: "
        f"{old} → {body.result}",
        changes={"inspection_id": inspection.id, "reason": body.reason},
    )
    db.commit()
    return get_inspection(db, principal, inspection.id)


# --------------------------------------------------------------------------- photos


def add_photo(
    db: Session,
    storage: ObjectStorage,
    principal: Principal,
    inspection_id: uuid.UUID,
    *,
    raw: bytes,
    filename: str | None,
    item_id: uuid.UUID | None,
    caption: str | None,
) -> PhotoRead:
    inspection, _ = _load(db, principal, inspection_id)
    _require_editable(principal, inspection)
    if item_id and not db.scalar(
        select(InspectionItem.id).where(
            InspectionItem.id == item_id, InspectionItem.inspection_id == inspection.id
        )
    ):
        raise NotFoundError("Checklist item not found.")
    count = db.scalar(
        select(func.count())
        .select_from(InspectionPhoto)
        .where(InspectionPhoto.inspection_id == inspection.id)
    )
    if (count or 0) >= MAX_PHOTOS_PER_INSPECTION:
        raise ConflictError(f"An inspection can have at most {MAX_PHOTOS_PER_INSPECTION} photos.")

    image = process_photo(raw)
    file_id = uuid.uuid4()
    base = f"org/{principal.organisation_id}/inspections/{inspection.id}/{file_id}"
    storage.put(f"{base}.jpg", image.data, image.content_type)
    storage.put(f"{base}_thumb.jpg", image.thumbnail, image.content_type)
    stored = StoredFile(
        id=file_id,
        organisation_id=principal.organisation_id,
        purpose="inspection_photo",
        storage_key=f"{base}.jpg",
        thumbnail_key=f"{base}_thumb.jpg",
        content_type=image.content_type,
        size_bytes=len(image.data),
        width=image.width,
        height=image.height,
        sha256=image.sha256,
        original_filename=(filename or "")[:255] or None,
        uploaded_by_user_id=principal.user_id,
    )
    photo = InspectionPhoto(
        inspection_id=inspection.id, item_id=item_id, file_id=file_id, caption=caption
    )
    db.add(stored)
    db.flush()
    db.add(photo)
    db.commit()
    return PhotoRead(
        id=photo.id, file_id=file_id, item_id=item_id, caption=caption, created_at=photo.created_at
    )


def delete_photo(
    db: Session,
    storage: ObjectStorage,
    principal: Principal,
    inspection_id: uuid.UUID,
    photo_id: uuid.UUID,
) -> None:
    """Only while the inspection is a draft; submitted evidence is never removed."""
    inspection, _ = _load(db, principal, inspection_id)
    _require_editable(principal, inspection)
    photo = db.scalar(
        select(InspectionPhoto).where(
            InspectionPhoto.id == photo_id, InspectionPhoto.inspection_id == inspection.id
        )
    )
    if photo is None:
        raise NotFoundError("Photo not found.")
    stored = db.get_one(StoredFile, photo.file_id)
    db.delete(photo)
    db.delete(stored)
    db.commit()
    for key in (stored.storage_key, stored.thumbnail_key):
        if key:
            storage.delete(key)


def authorise_file(db: Session, principal: Principal, file: StoredFile) -> None:
    """Raise NotFound unless the caller may see the record that owns this file."""
    if file.purpose == "inspection_photo":
        inspection_id = db.scalar(
            select(InspectionPhoto.inspection_id).where(InspectionPhoto.file_id == file.id)
        )
        if inspection_id is None:
            raise NotFoundError("File not found.")
        _load(db, principal, inspection_id)
        return
    raise NotFoundError("File not found.")
