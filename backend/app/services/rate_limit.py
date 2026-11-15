"""Fixed-window rate limiting backed by Redis.

If Redis is unavailable the limiter fails open (allows the request) and logs a
warning: losing sign-in for the whole workshop is worse than briefly losing
throttling. Monitoring should alert on the warning.
"""

import hashlib
import logging

from redis import Redis
from redis.exceptions import RedisError

from app.core.errors import AppError

logger = logging.getLogger(__name__)


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


def _key(bucket: str, identifier: str) -> str:
    # Hash identifiers so emails/IPs are not stored in Redis in clear text.
    digest = hashlib.sha256(identifier.lower().encode()).hexdigest()[:32]
    return f"rl:{bucket}:{digest}"


def hit(redis: Redis, bucket: str, identifier: str, *, limit: int, window_seconds: int) -> bool:
    """Count one attempt. Returns False when the limit has been exceeded."""
    key = _key(bucket, identifier)
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        count, _ = pipe.execute()
    except RedisError:
        logger.warning("rate_limit_unavailable", extra={"bucket": bucket})
        return True
    return int(count) <= limit


def enforce(
    redis: Redis,
    bucket: str,
    identifier: str,
    *,
    limit: int,
    window_seconds: int,
    enabled: bool = True,
) -> None:
    if enabled and not hit(redis, bucket, identifier, limit=limit, window_seconds=window_seconds):
        raise RateLimitedError(
            "Too many attempts. Please wait a few minutes and try again.",
            details={"retry_after_seconds": window_seconds},
        )


def reset(redis: Redis, bucket: str, identifier: str) -> None:
    try:
        redis.delete(_key(bucket, identifier))
    except RedisError:
        logger.warning("rate_limit_unavailable", extra={"bucket": bucket})
