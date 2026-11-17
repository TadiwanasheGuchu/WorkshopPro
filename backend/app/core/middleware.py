"""Request ID, request logging, and secure response headers."""

import hmac
import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.context import client_ip_var, request_id_var, user_agent_var, valid_ip
from app.core.security import CSRF_COOKIE, CSRF_HEADER

logger = logging.getLogger("workshoppro.request")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), geolocation=(), microphone=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


# Server-to-server callbacks authenticate with a signature (checked in the route) and use
# no cookies, so the cookie-based CSRF check does not apply to them.
CSRF_EXEMPT_PREFIXES = ("/api/v1/webhooks/",)


def _csrf_cookie_matches(request: Request) -> bool:
    """Double-submit check: the X-CSRF-Token header must equal the CSRF cookie.

    Cross-site pages can neither read our cookie nor set custom headers without a CORS
    preflight, so a match proves the request came from our own frontend. For
    authenticated requests the auth dependency additionally binds the token to the
    session (see app/auth/dependencies.py).
    """
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    return bool(cookie) and hmac.compare_digest(cookie.encode(), header.encode())


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, hsts: bool) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        request_id_var.set(request_id)
        client_ip_var.set(valid_ip(request.client.host if request.client else None))
        user_agent_var.set(request.headers.get("user-agent", "")[:300] or None)

        if (
            request.method not in SAFE_METHODS
            and not request.url.path.startswith(CSRF_EXEMPT_PREFIXES)
            and not _csrf_cookie_matches(request)
        ):
            response: Response = JSONResponse(
                {
                    "error": {
                        "code": "csrf_failed",
                        "message": "Missing or invalid CSRF token. Refresh the page and try again.",
                        "details": None,
                        "request_id": request_id,
                    }
                },
                status_code=403,
            )
            response.headers["X-Request-ID"] = request_id
            return response

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-ID"] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if self.hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )

        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
