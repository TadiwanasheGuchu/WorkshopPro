"""Small helpers shared by services."""

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.schemas.common import PageParams


def get_scoped[T](
    db: Session, model: type[T], entity_id: uuid.UUID, organisation_id: uuid.UUID
) -> T:
    """Fetch a record by id within the caller's organisation.

    Records belonging to another organisation are reported as not found, so the API
    never confirms that another tenant's record exists.
    """
    obj = db.scalar(
        select(model).where(
            model.id == entity_id,  # type: ignore[attr-defined]
            model.organisation_id == organisation_id,  # type: ignore[attr-defined]
        )
    )
    if obj is None:
        raise NotFoundError(f"{model.__name__} not found.")
    return obj


def apply_changes(obj: object, data: dict[str, Any]) -> dict[str, list[Any]]:
    """Set attributes from `data`; return {"field": [old, new]} for changed fields."""
    changes: dict[str, list[Any]] = {}
    for key, value in data.items():
        old = getattr(obj, key)
        if old != value:
            changes[key] = [old, value]
            setattr(obj, key, value)
    return changes


def paginate(db: Session, stmt: Select[Any], params: PageParams) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.limit(params.page_size).offset(params.offset)))
    return items, total
