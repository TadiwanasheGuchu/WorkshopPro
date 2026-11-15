"""Cross-cutting API behaviour: error envelope, request IDs, security headers."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import InvalidStateTransitionError
from app.main import create_app


def _app_with_test_routes() -> FastAPI:
    app = create_app()

    @app.get("/_test/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    @app.get("/_test/transition")
    def transition() -> None:
        raise InvalidStateTransitionError(
            "Cannot move from 'vehicle_received' to 'completed'.",
            details={"from": "vehicle_received", "to": "completed"},
        )

    @app.get("/_test/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    return app


client = TestClient(_app_with_test_routes(), raise_server_exceptions=False)


def test_not_found_uses_error_envelope() -> None:
    res = client.get("/api/v1/does-not-exist")

    assert res.status_code == 404
    error = res.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == res.headers["x-request-id"]


def test_validation_error_envelope() -> None:
    res = client.get("/_test/items/not-a-number")

    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["path", "item_id"]


def test_business_error_envelope() -> None:
    res = client.get("/_test/transition")

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "invalid_state_transition"
    assert res.json()["error"]["details"] == {"from": "vehicle_received", "to": "completed"}


def test_unhandled_error_does_not_leak_internals() -> None:
    res = client.get("/_test/boom")

    assert res.status_code == 500
    assert res.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in res.text
    assert "Traceback" not in res.text


def test_request_id_is_propagated_when_safe() -> None:
    res = client.get("/api/v1/health/live", headers={"X-Request-ID": "abc-123"})
    assert res.headers["x-request-id"] == "abc-123"


def test_unsafe_request_id_is_replaced() -> None:
    res = client.get("/api/v1/health/live", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert res.headers["x-request-id"] != "<script>alert(1)</script>"
    assert len(res.headers["x-request-id"]) == 32


def test_security_headers_present() -> None:
    res = client.get("/api/v1/health/live")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in res.headers  # only in production


def test_cors_rejects_unknown_origin() -> None:
    res = client.get("/api/v1/health/live", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in res.headers
