"""Inspection summaries for job card pages (kept separate to avoid import cycles)."""

import uuid
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Inspection, InspectionItem, User
from app.schemas.inspection import InspectionSummary

RESULTS = ("pass", "attention", "fail", "not_inspected")


def counts(results: list[str]) -> dict[str, int]:
    c = Counter(results)
    return {r: c.get(r, 0) for r in RESULTS}


def summaries_for_job(db: Session, job_id: uuid.UUID) -> list[InspectionSummary]:
    inspections = list(
        db.scalars(
            select(Inspection)
            .where(Inspection.job_card_id == job_id)
            .order_by(Inspection.created_at)
        )
    )
    if not inspections:
        return []
    results: dict[uuid.UUID, list[str]] = defaultdict(list)
    for iid, result in db.execute(
        select(InspectionItem.inspection_id, InspectionItem.result).where(
            InspectionItem.inspection_id.in_([i.id for i in inspections])
        )
    ):
        results[iid].append(result)
    starters = {i.started_by_user_id for i in inspections if i.started_by_user_id}
    names = (
        dict(db.execute(select(User.id, User.full_name).where(User.id.in_(starters))).all())
        if starters
        else {}
    )
    return [
        InspectionSummary(
            id=i.id,
            kind=i.kind,  # type: ignore[arg-type]
            status=i.status,  # type: ignore[arg-type]
            template_name=i.template_name,
            started_by=names.get(i.started_by_user_id) if i.started_by_user_id else None,
            submitted_at=i.submitted_at,
            counts=counts(results[i.id]),  # type: ignore[arg-type]
        )
        for i in inspections
    ]
