import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentPrincipal, DbSession, IdempotencyKey
from app.schemas.inventory import JobPartsRead, JobPartsRequest, JobPartsReturn, ReleaseRequest
from app.services import job_parts

router = APIRouter(prefix="/job-cards/{job_id}/parts", tags=["job parts"])


def _replayed(response: Response, created: bool) -> None:
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"


@router.get(
    "",
    response_model=JobPartsRead,
    summary="Parts reserved for and fitted to the job",
)
def get(job_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> JobPartsRead:
    return job_parts.read(db, principal, job_id)


@router.post(
    "/reservations",
    response_model=JobPartsRead,
    status_code=status.HTTP_201_CREATED,
    summary="Reserve stock for the job",
    description=(
        "Only for authorised jobs (approved quotation or approval exception). Reserves "
        "available stock at a location in the job's branch. Requires an Idempotency-Key."
    ),
)
def reserve(
    job_id: uuid.UUID,
    body: JobPartsRequest,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> JobPartsRead:
    result, created = job_parts.reserve(db, principal, job_id, body, idempotency_key)
    _replayed(response, created)
    return result


@router.post(
    "/reservations/{reservation_id}/release",
    response_model=JobPartsRead,
    summary="Release what is still reserved",
)
def release(
    job_id: uuid.UUID,
    reservation_id: uuid.UUID,
    body: ReleaseRequest,
    principal: CurrentPrincipal,
    db: DbSession,
) -> JobPartsRead:
    return job_parts.release(db, principal, job_id, reservation_id, body)


@router.post(
    "/issues",
    response_model=JobPartsRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue parts that are fitted",
    description=(
        "Consumes stock: draws first on the job's reservations at that location, then on "
        "free stock. Only for authorised jobs. Requires an Idempotency-Key."
    ),
)
def issue(
    job_id: uuid.UUID,
    body: JobPartsRequest,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> JobPartsRead:
    result, created = job_parts.issue(db, principal, job_id, body, idempotency_key)
    _replayed(response, created)
    return result


@router.post(
    "/returns",
    response_model=JobPartsRead,
    status_code=status.HTTP_201_CREATED,
    summary="Return unused parts to stock",
    description="Up to what was issued to the job. A reason is required.",
)
def return_parts(
    job_id: uuid.UUID,
    body: JobPartsReturn,
    principal: CurrentPrincipal,
    db: DbSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> JobPartsRead:
    result, created = job_parts.return_parts(db, principal, job_id, body, idempotency_key)
    _replayed(response, created)
    return result
