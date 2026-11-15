from fastapi import APIRouter, Depends, Response, status
from redis import Redis
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import get_db
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health import check_readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Returns 200 while the API process is running. Does not check dependencies.",
)
def live() -> LivenessResponse:
    return LivenessResponse(status="ok", service=get_settings().app_name, version=__version__)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Checks PostgreSQL and Redis. Returns 503 if any dependency is unavailable. "
        "Failure details are intentionally generic; see server logs for causes."
    ),
    responses={503: {"model": ReadinessResponse}},
)
def ready(
    response: Response,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ReadinessResponse:
    result = check_readiness(db, redis)
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
