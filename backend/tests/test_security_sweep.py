"""Authentication sweep over every API operation (CLAUDE.md §8, §13).

Generated from the OpenAPI document, so a new endpoint is covered automatically:
- Anonymous requests must be rejected (401) unless the operation is on the PUBLIC list.
- A signed-in customer portal session must be rejected by every staff operation.
- A staff session must be rejected by every customer portal operation.
A new public endpoint has to be added to PUBLIC deliberately, with a reason.
"""

import re
import uuid
from typing import Any

import pytest

from app.integrations.email import InMemoryEmailSender
from tests.conftest import Api, OrgFixture

PUBLIC: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/health/live"): "liveness probe",
    ("GET", "/api/v1/health/ready"): "readiness probe",
    ("GET", "/api/v1/auth/csrf"): "issues the CSRF cookie before sign-in",
    ("POST", "/api/v1/auth/login"): "sign-in",
    ("POST", "/api/v1/auth/password-reset/request"): "forgotten password",
    ("POST", "/api/v1/auth/password-reset/confirm"): "single-use reset token",
    ("POST", "/api/v1/auth/tokens/inspect"): "checks a reset/invitation token before use",
    ("POST", "/api/v1/auth/invitations/accept"): "single-use invitation token",
    ("POST", "/api/v1/public/quotations/view"): "customer quotation link token",
    ("POST", "/api/v1/public/quotations/decision"): "customer quotation link token",
    ("POST", "/api/v1/public/quotations/pdf"): "customer quotation link token",
    ("GET", "/api/v1/webhooks/whatsapp"): "Meta webhook verification (verify token)",
    ("POST", "/api/v1/webhooks/whatsapp"): "Meta status callbacks (HMAC signature)",
    ("POST", "/api/v1/portal/auth/request-link"): "customer requests a sign-in link",
    ("POST", "/api/v1/portal/auth/consume"): "single-use customer sign-in token",
}

# Sign-out endpoints are harmless without a session; they may answer 204 or 401.
SIGN_OUT = {("POST", "/api/v1/auth/logout"), ("POST", "/api/v1/portal/auth/logout")}

PARAM_VALUES = {"event": "vehicle_received"}


def _operations(app: Any) -> list[tuple[str, str]]:
    spec = app.openapi()
    return sorted(
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if method in ("get", "post", "put", "patch", "delete")
    )


def _url(path: str) -> str:
    def fill(match: re.Match[str]) -> str:
        return PARAM_VALUES.get(match.group(1), str(uuid.uuid4()))

    return re.sub(r"\{(\w+)\}", fill, path).removeprefix("/api/v1")


def _call(api: Api, method: str, path: str) -> int:
    url = _url(path)
    if method in ("GET", "DELETE"):
        return api.request(method, url).status_code
    return api.request(method, url, json={}).status_code


@pytest.mark.usefixtures("db")
def test_every_operation_requires_authentication_unless_public(app: Any, new_api: Any) -> None:
    anonymous: Api = new_api()
    operations = _operations(app)
    assert len(operations) > 150  # the sweep must actually cover the API
    open_ops = set()
    for method, path in operations:
        if (method, path) in SIGN_OUT:
            continue
        if _call(anonymous, method, path) != 401:
            open_ops.add((method, path))
    unexpected = open_ops - set(PUBLIC)
    assert not unexpected, f"Operations reachable without signing in: {sorted(unexpected)}"


def test_portal_and_staff_sessions_are_separate(
    app: Any, owner_api: Api, org: OrgFixture, new_api: Any, outbox: InMemoryEmailSender
) -> None:
    c = owner_api.post(
        "/customers",
        json={
            "customer_type": "individual",
            "last_name": "Sweep",
            "contacts": [{"kind": "email", "value": "sweep@example.com"}],
        },
    ).json()
    owner_api.post(f"/customers/{c['id']}/portal/invite", json={"email": "sweep@example.com"})
    token = outbox.outbox[-1].text.split("#token=")[1].split()[0]
    customer: Api = new_api()
    assert customer.post("/portal/auth/consume", json={"token": token}).status_code == 204

    leaks = []
    for method, path in _operations(app):
        if (method, path) in PUBLIC or (method, path) in SIGN_OUT:
            continue
        portal_op = path.startswith("/api/v1/portal/")
        caller = owner_api if portal_op else customer
        if _call(caller, method, path) != 401:
            leaks.append((method, path, "staff session" if portal_op else "portal session"))
    assert not leaks, f"Session reached the wrong side: {leaks}"


def test_security_headers(client: Any) -> None:
    res = client.get("/api/v1/health/live")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in res.headers
    assert "X-Request-ID" in res.headers
