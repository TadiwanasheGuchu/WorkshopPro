import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession, Paging
from app.schemas.common import Page
from app.schemas.job_card import (
    AssignableUser,
    AssignmentRequest,
    ExceptionCreate,
    ExceptionRevoke,
    JobCardCreate,
    JobCardDetail,
    JobCardSummary,
    JobCardUpdate,
    JobSummaryCounts,
    NoteCreate,
    NoteRead,
    TransitionRequest,
)
from app.services import job_cards
from app.services.job_workflow import JobStatus

router = APIRouter(prefix="/job-cards", tags=["job cards"])

_VISIBILITY = (
    "Users with `job_cards.view` see every job in their branches; users with only "
    "`job_cards.work` see jobs assigned to them."
)


@router.get(
    "", response_model=Page[JobCardSummary], summary="List job cards", description=_VISIBILITY
)
def list_job_cards(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    branch_id: uuid.UUID | None = None,
    status: Annotated[list[JobStatus] | None, Query()] = None,
    open_only: bool = False,
    assigned_to_me: bool = False,
    overdue: bool = False,
    vehicle_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[JobCardSummary]:
    items, total = job_cards.list_job_cards(
        db,
        principal,
        paging,
        branch_id=branch_id,
        statuses=status,
        open_only=open_only,
        assigned_to_me=assigned_to_me,
        overdue=overdue,
        vehicle_id=vehicle_id,
        customer_id=customer_id,
        search=search,
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)


@router.get(
    "/summary",
    response_model=JobSummaryCounts,
    summary="Job counts for the dashboard",
    description=(
        "Counts only jobs visible to the caller. 'Today' uses the organisation's time zone."
    ),
)
def summary(
    principal: CurrentPrincipal, db: DbSession, branch_id: uuid.UUID | None = None
) -> JobSummaryCounts:
    return job_cards.summary_counts(db, principal, branch_id=branch_id)


@router.post(
    "",
    response_model=JobCardDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Receive a vehicle (open a job card)",
    description=(
        "Allocates the next organisation-scoped job number. A vehicle can have only one open "
        "job card. A lower odometer reading than last recorded needs `odometer_correction_reason`."
    ),
)
def create_job_card(
    body: JobCardCreate, principal: CurrentPrincipal, db: DbSession
) -> JobCardDetail:
    return job_cards.create_job_card(db, principal, body)


@router.get(
    "/{job_id}", response_model=JobCardDetail, summary="Job card details", description=_VISIBILITY
)
def get_job_card(job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> JobCardDetail:
    return job_cards.get_job_card(db, principal, job_id)


@router.patch(
    "/{job_id}",
    response_model=JobCardDetail,
    summary="Update job details",
    description=(
        "Send the `version` you loaded (409 `stale_version` if someone else changed the job). "
        "Assigned mechanics may only update `diagnosis` and `work_performed`."
    ),
)
def update_job_card(
    job_id: uuid.UUID, body: JobCardUpdate, principal: CurrentPrincipal, db: DbSession
) -> JobCardDetail:
    return job_cards.update_job_card(db, principal, job_id, body)


@router.post(
    "/{job_id}/transitions",
    response_model=JobCardDetail,
    summary="Change job status",
    description=(
        "Only transitions in the workflow table are accepted (409 `invalid_state_transition`). "
        "Entering 'awaiting parts' or 'repair in progress' needs customer approval or an "
        "active approval exception (409 `approval_required`). Completing requires "
        "`collected_by_name`; cancelling requires `cancellation_reason`."
    ),
)
def transition(
    job_id: uuid.UUID, body: TransitionRequest, principal: CurrentPrincipal, db: DbSession
) -> JobCardDetail:
    return job_cards.transition(db, principal, job_id, body)


@router.get(
    "/{job_id}/assignable-users",
    response_model=list[AssignableUser],
    summary="Users who can be assigned",
    description=(
        "Active users with 'work on assigned jobs' at this job's branch, with open job counts."
    ),
)
def assignable_users(
    job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> list[AssignableUser]:
    return job_cards.assignable_users(db, principal, job_id)


@router.post("/{job_id}/assignments", response_model=JobCardDetail, summary="Assign a mechanic")
def assign(
    job_id: uuid.UUID, body: AssignmentRequest, principal: CurrentPrincipal, db: DbSession
) -> JobCardDetail:
    return job_cards.assign(db, principal, job_id, body.user_id)


@router.delete(
    "/{job_id}/assignments/{user_id}",
    response_model=JobCardDetail,
    summary="Unassign a mechanic",
    description="Closes the assignment; the record is kept in the job's history.",
)
def unassign(
    job_id: uuid.UUID, user_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession
) -> JobCardDetail:
    return job_cards.unassign(db, principal, job_id, user_id)


@router.post(
    "/{job_id}/notes",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a work note",
    description="Notes are append-only.",
)
def add_note(
    job_id: uuid.UUID, body: NoteCreate, principal: CurrentPrincipal, db: DbSession
) -> NoteRead:
    return job_cards.add_note(db, principal, job_id, body)


@router.post(
    "/{job_id}/approval-exceptions",
    response_model=JobCardDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Authorise work without quotation approval",
    description="Records who authorised it, when, why, and exactly which work is covered.",
)
def authorise_exception(
    job_id: uuid.UUID, body: ExceptionCreate, principal: CurrentPrincipal, db: DbSession
) -> JobCardDetail:
    return job_cards.authorise_exception(db, principal, job_id, body)


@router.post(
    "/{job_id}/approval-exceptions/{exception_id}/revoke",
    response_model=JobCardDetail,
    summary="Revoke an approval exception",
)
def revoke_exception(
    job_id: uuid.UUID,
    exception_id: uuid.UUID,
    body: ExceptionRevoke,
    principal: CurrentPrincipal,
    db: DbSession,
) -> JobCardDetail:
    return job_cards.revoke_exception(db, principal, job_id, exception_id, body.reason)
