"""Customer-readable vehicle inspection report."""

import logging
import uuid
from collections import OrderedDict
from collections.abc import Callable
from io import BytesIO

from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Image, Spacer, Table

from app.documents.base import (
    CONTENT_W,
    Document,
    OrgInfo,
    Party,
    data_table,
    heading,
    p,
    paragraph_block,
    small,
)
from app.schemas.inspection import InspectionDetail

logger = logging.getLogger(__name__)

RESULT = {
    "pass": "Pass",
    "attention": "Attention required",
    "fail": "Failed",
    "not_inspected": "Not inspected",
}
TITLE = {
    "intake": "Vehicle inspection",
    "quality": "Quality inspection",
    "other": "Inspection report",
}
THUMB = 30 * mm
MAX_PHOTOS_PER_ITEM = 4

PhotoLoader = Callable[[uuid.UUID], bytes | None]


def _photos(file_ids: list[uuid.UUID], load: PhotoLoader) -> Flowable | None:
    images: list[Flowable] = []
    for file_id in file_ids[:MAX_PHOTOS_PER_ITEM]:
        try:
            data = load(file_id)
        except Exception:  # a missing photo must not stop the report
            logger.warning("inspection photo unavailable", extra={"file_id": str(file_id)})
            data = None
        if data:
            img = Image(BytesIO(data))
            ratio = img.imageHeight / img.imageWidth if img.imageWidth else 1
            img.drawWidth, img.drawHeight = THUMB, THUMB * ratio
            images.append(img)
    if not images:
        return None
    t = Table([images], colWidths=[THUMB + 3 * mm] * len(images), hAlign="LEFT")
    return t


def inspection(
    org: OrgInfo, ins: InspectionDetail, customer: Party, load_photo: PhotoLoader
) -> bytes:
    sections: OrderedDict[str, list] = OrderedDict()
    for item in ins.items:
        sections.setdefault(item.section, []).append(item)

    counts = ins.counts
    summary_line = (
        f"{counts.get('pass', 0)} passed · {counts.get('attention', 0)} need attention · "
        f"{counts.get('fail', 0)} failed · {counts.get('not_inspected', 0)} not inspected"
    )
    body: list[Flowable] = [p(summary_line, "bold"), Spacer(1, 2 * mm)]
    body += paragraph_block("Inspector's summary", ins.summary)

    for section, items in sections.items():
        body.append(heading(section))
        rows = []
        for item in items:
            notes: list[Flowable] = [p(item.notes)] if item.notes else [small("—")]
            photos = _photos([ph.file_id for ph in item.photos], load_photo)
            if photos:
                notes.append(photos)
            rows.append([item.label, RESULT[item.result], notes])
        body.append(
            data_table(
                ["Item", "Result", "Notes"],
                rows,
                [55 * mm, 32 * mm, CONTENT_W - 87 * mm],
            )
        )

    general = _photos([ph.file_id for ph in ins.general_photos], load_photo)
    if general:
        body += [heading("Photos"), general]

    if ins.amendments:
        body.append(heading("Changes after submission"))
        body.append(
            data_table(
                ["Item", "Change", "Reason", "By"],
                [
                    [
                        a.item_label,
                        f"{RESULT[a.old_result]} → {RESULT[a.new_result]}",
                        a.reason,
                        f"{a.amended_by}, {org.datetime(a.amended_at)}",
                    ]
                    for a in ins.amendments
                ],
                [40 * mm, 45 * mm, CONTENT_W - 125 * mm, 40 * mm],
            )
        )

    signed = (
        f"Submitted by {ins.submitted_by or '—'} on {org.datetime(ins.submitted_at)}."
        if ins.status == "submitted"
        else None
    )
    if signed:
        body += [Spacer(1, 4 * mm), small(signed)]

    vehicle = ins.vehicle
    vehicle_rows: list[tuple[str, str]] = []
    title = " ".join(str(vehicle.get(k)) for k in ("year", "make", "model") if vehicle.get(k))
    if title:
        vehicle_rows.append(("", title))
    if vehicle.get("registration_number"):
        vehicle_rows.append(("Registration", str(vehicle["registration_number"])))
    if vehicle.get("vin"):
        vehicle_rows.append(("VIN", str(vehicle["vin"])))
    if ins.odometer_km is not None:
        vehicle_rows.append(("Odometer", f"{ins.odometer_km:,} km"))

    return Document(
        org=org,
        title=TITLE.get(ins.kind, "Inspection report"),
        meta=[
            ("Job", ins.job_card.get("job_number") or ins.job_card.get("name", "")),
            ("Date", org.date(ins.submitted_at or ins.created_at)),
            ("Checklist", ins.template_name),
            ("Branch", ins.branch_name),
        ],
        customer=customer,
        vehicle=vehicle_rows,
        notice=None
        if ins.status == "submitted"
        else "Draft: this inspection has not been completed yet.",
        body=body,
    ).render()
