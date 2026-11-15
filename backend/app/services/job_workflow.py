"""Job card status workflow (CLAUDE.md §3.4).

The transition table is the single source of truth; clients can only request a target
status, and the service checks it against this table, the caller's permissions and
the approval rule.
"""

from enum import StrEnum


class JobStatus(StrEnum):
    VEHICLE_RECEIVED = "vehicle_received"
    INSPECTION_PENDING = "inspection_pending"
    DIAGNOSIS_IN_PROGRESS = "diagnosis_in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_PARTS = "awaiting_parts"
    REPAIR_IN_PROGRESS = "repair_in_progress"
    QUALITY_INSPECTION = "quality_inspection"
    READY_FOR_COLLECTION = "ready_for_collection"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


S = JobStatus

TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    S.VEHICLE_RECEIVED: frozenset({S.INSPECTION_PENDING, S.DIAGNOSIS_IN_PROGRESS, S.CANCELLED}),
    S.INSPECTION_PENDING: frozenset({S.DIAGNOSIS_IN_PROGRESS, S.CANCELLED}),
    S.DIAGNOSIS_IN_PROGRESS: frozenset(
        {S.AWAITING_APPROVAL, S.AWAITING_PARTS, S.REPAIR_IN_PROGRESS, S.CANCELLED}
    ),
    S.AWAITING_APPROVAL: frozenset(
        {S.DIAGNOSIS_IN_PROGRESS, S.AWAITING_PARTS, S.REPAIR_IN_PROGRESS, S.CANCELLED}
    ),
    S.AWAITING_PARTS: frozenset({S.REPAIR_IN_PROGRESS, S.CANCELLED}),
    S.REPAIR_IN_PROGRESS: frozenset({S.AWAITING_PARTS, S.QUALITY_INSPECTION}),
    # Failing the quality check sends the job back to repair.
    S.QUALITY_INSPECTION: frozenset({S.REPAIR_IN_PROGRESS, S.READY_FOR_COLLECTION}),
    S.READY_FOR_COLLECTION: frozenset({S.COMPLETED, S.REPAIR_IN_PROGRESS}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
}

TERMINAL: frozenset[JobStatus] = frozenset({S.COMPLETED, S.CANCELLED})

# Moves an assigned mechanic (job_cards.work) may make. Everything else needs
# job_cards.manage: quality sign-off, handover, cancellation, re-opening.
MECHANIC_TRANSITIONS: frozenset[tuple[JobStatus, JobStatus]] = frozenset(
    {
        (S.VEHICLE_RECEIVED, S.DIAGNOSIS_IN_PROGRESS),
        (S.INSPECTION_PENDING, S.DIAGNOSIS_IN_PROGRESS),
        (S.DIAGNOSIS_IN_PROGRESS, S.AWAITING_APPROVAL),
        (S.DIAGNOSIS_IN_PROGRESS, S.REPAIR_IN_PROGRESS),
        (S.AWAITING_PARTS, S.REPAIR_IN_PROGRESS),
        (S.REPAIR_IN_PROGRESS, S.AWAITING_PARTS),
        (S.REPAIR_IN_PROGRESS, S.QUALITY_INSPECTION),
    }
)

# Entering these statuses means chargeable work or parts are committed, so the job
# needs customer approval: an approved quotation (Phase 3) or an active, authorised
# approval exception. Moving between them (repair <-> awaiting parts) is already covered.
REQUIRES_APPROVAL: frozenset[JobStatus] = frozenset({S.AWAITING_PARTS, S.REPAIR_IN_PROGRESS})
APPROVED_STATES: frozenset[JobStatus] = frozenset(
    {S.AWAITING_PARTS, S.REPAIR_IN_PROGRESS, S.QUALITY_INSPECTION, S.READY_FOR_COLLECTION}
)

LABELS: dict[JobStatus, str] = {
    S.VEHICLE_RECEIVED: "Vehicle received",
    S.INSPECTION_PENDING: "Inspection pending",
    S.DIAGNOSIS_IN_PROGRESS: "Diagnosis in progress",
    S.AWAITING_APPROVAL: "Awaiting quotation approval",
    S.AWAITING_PARTS: "Awaiting parts",
    S.REPAIR_IN_PROGRESS: "Repair in progress",
    S.QUALITY_INSPECTION: "Quality inspection",
    S.READY_FOR_COLLECTION: "Ready for collection",
    S.COMPLETED: "Completed / collected",
    S.CANCELLED: "Cancelled",
}


def is_valid(current: JobStatus, target: JobStatus) -> bool:
    return target in TRANSITIONS[current]


def needs_approval(current: JobStatus, target: JobStatus) -> bool:
    return target in REQUIRES_APPROVAL and current not in APPROVED_STATES
