"""Inspection templates (checklists)."""

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, PermissionDeniedError
from app.core.time import utcnow
from app.models import InspectionTemplate, InspectionTemplateItem
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.inspection import TemplateInput, TemplateItemRead, TemplateRead
from app.services import audit
from app.services.common import get_scoped
from app.services.default_inspection import (
    DEFAULT_ITEMS,
    DEFAULT_TEMPLATE_DESCRIPTION,
    DEFAULT_TEMPLATE_NAME,
)


def seed_default(db: Session, organisation_id: uuid.UUID) -> InspectionTemplate:
    template = InspectionTemplate(
        organisation_id=organisation_id,
        name=DEFAULT_TEMPLATE_NAME,
        description=DEFAULT_TEMPLATE_DESCRIPTION,
        is_default=True,
    )
    db.add(template)
    db.flush()
    db.add_all(
        InspectionTemplateItem(
            template_id=template.id, section=s, label=label, guidance=g, position=i
        )
        for i, (s, label, g) in enumerate(DEFAULT_ITEMS)
    )
    return template


def _require_read(principal: Principal) -> None:
    if not (
        principal.can_in_any_branch(P.INSPECTIONS_PERFORM)
        or principal.can(P.INSPECTION_TEMPLATES_MANAGE)
    ):
        raise PermissionDeniedError("You do not have permission to view inspection templates.")


def _items(db: Session, template_id: uuid.UUID) -> list[InspectionTemplateItem]:
    return list(
        db.scalars(
            select(InspectionTemplateItem)
            .where(InspectionTemplateItem.template_id == template_id)
            .order_by(InspectionTemplateItem.position)
        )
    )


def _read(db: Session, t: InspectionTemplate, *, with_items: bool) -> TemplateRead:
    items = _items(db, t.id)
    return TemplateRead(
        id=t.id,
        name=t.name,
        description=t.description,
        is_default=t.is_default,
        archived_at=t.archived_at,
        item_count=len(items),
        items=[
            TemplateItemRead(id=i.id, section=i.section, label=i.label, guidance=i.guidance)
            for i in items
        ]
        if with_items
        else None,
    )


def list_templates(
    db: Session, principal: Principal, *, include_archived: bool = False
) -> list[TemplateRead]:
    _require_read(principal)
    stmt = select(InspectionTemplate).where(
        InspectionTemplate.organisation_id == principal.organisation_id
    )
    if not include_archived:
        stmt = stmt.where(InspectionTemplate.archived_at.is_(None))
    templates = db.scalars(
        stmt.order_by(InspectionTemplate.is_default.desc(), InspectionTemplate.name)
    )
    return [_read(db, t, with_items=False) for t in templates]


def get_template(db: Session, principal: Principal, template_id: uuid.UUID) -> TemplateRead:
    _require_read(principal)
    t = get_scoped(db, InspectionTemplate, template_id, principal.organisation_id)
    return _read(db, t, with_items=True)


def _write_items(db: Session, template: InspectionTemplate, body: TemplateInput) -> None:
    db.execute(
        delete(InspectionTemplateItem).where(InspectionTemplateItem.template_id == template.id)
    )
    db.add_all(
        InspectionTemplateItem(
            template_id=template.id,
            section=i.section,
            label=i.label,
            guidance=i.guidance,
            position=pos,
        )
        for pos, i in enumerate(body.items)
    )


def _set_default(db: Session, template: InspectionTemplate) -> None:
    db.execute(
        update(InspectionTemplate)
        .where(
            InspectionTemplate.organisation_id == template.organisation_id,
            InspectionTemplate.id != template.id,
        )
        .values(is_default=False)
    )


def save_template(
    db: Session, principal: Principal, body: TemplateInput, template_id: uuid.UUID | None = None
) -> TemplateRead:
    """Create (template_id None) or replace a template. Past inspections keep their own copy
    of the checklist, so editing a template never changes them."""
    principal.require(P.INSPECTION_TEMPLATES_MANAGE)
    if template_id:
        template = get_scoped(db, InspectionTemplate, template_id, principal.organisation_id)
        if template.archived_at is not None:
            raise ConflictError("Restore this template before editing it.")
        template.name, template.description = body.name, body.description
    else:
        template = InspectionTemplate(
            organisation_id=principal.organisation_id, name=body.name, description=body.description
        )
        db.add(template)
    template.is_default = body.is_default or template.is_default
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A template with this name already exists.") from exc
    if body.is_default:
        _set_default(db, template)
    _write_items(db, template, body)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="inspection_template.updated" if template_id else "inspection_template.created",
        entity_type="inspection_template",
        entity_id=template.id,
        summary=f"Inspection template {template.name} {'updated' if template_id else 'created'} "
        f"({len(body.items)} items)",
    )
    db.commit()
    return _read(db, template, with_items=True)


def set_archived(
    db: Session, principal: Principal, template_id: uuid.UUID, archived: bool
) -> TemplateRead:
    principal.require(P.INSPECTION_TEMPLATES_MANAGE)
    template = get_scoped(db, InspectionTemplate, template_id, principal.organisation_id)
    if archived and template.archived_at is None:
        active = db.scalar(
            select(func.count())
            .select_from(InspectionTemplate)
            .where(
                InspectionTemplate.organisation_id == principal.organisation_id,
                InspectionTemplate.archived_at.is_(None),
            )
        )
        if active == 1:
            raise ConflictError("Keep at least one active inspection template.")
        template.archived_at = utcnow()
        template.is_default = False
    elif not archived:
        template.archived_at = None
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An active template already uses this name.") from exc
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="inspection_template.archived" if archived else "inspection_template.restored",
        entity_type="inspection_template",
        entity_id=template.id,
        summary=f"Inspection template {template.name} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return _read(db, template, with_items=False)
