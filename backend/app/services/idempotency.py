"""Idempotency for operations where a duplicate request would cause harm (payments,
stock changes). The client sends an Idempotency-Key per intended operation; the server
stores it with a fingerprint of the request body.

- Same key, same body: the original result is returned (nothing applied twice).
- Same key, different body: rejected with 409 idempotency_key_reused.
"""

import hashlib
import json
from typing import Any

from app.core.errors import AppError


class IdempotencyConflictError(AppError):
    status_code = 409
    code = "idempotency_key_reused"


def fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def check_replay(stored_fingerprint: str, request_fingerprint: str) -> None:
    if stored_fingerprint != request_fingerprint:
        raise IdempotencyConflictError(
            "This Idempotency-Key was already used for a different request."
        )
