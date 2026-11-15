"""Dependency checks used by the readiness endpoint."""

import logging
import time
from collections.abc import Callable

from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.health import DependencyCheck, ReadinessResponse

logger = logging.getLogger(__name__)


def _timed(name: str, check: Callable[[], None]) -> DependencyCheck:
    start = time.perf_counter()
    try:
        check()
    except Exception as exc:
        # Log the cause server-side; never return connection strings or internals.
        logger.warning("readiness_check_failed", extra={"check": name, "error": type(exc).__name__})
        return DependencyCheck(status="error", detail="unavailable")
    return DependencyCheck(status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 1))


def check_readiness(db: Session, redis: Redis) -> ReadinessResponse:
    checks = {
        "database": _timed("database", lambda: db.execute(text("SELECT 1")).scalar_one()),
        "redis": _timed("redis", lambda: redis.ping()),
    }
    overall = "ok" if all(c.status == "ok" for c in checks.values()) else "error"
    return ReadinessResponse(status=overall, checks=checks)
