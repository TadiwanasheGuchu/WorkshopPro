import pytest
from fastapi.testclient import TestClient

from app.core.redis import get_redis
from app.db.session import get_db


class _BrokenSession:
    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise ConnectionError("postgresql://user:secret@db/x refused")


class _OkRedis:
    def ping(self) -> bool:
        return True


def test_liveness(client: TestClient) -> None:
    res = client.get("/api/v1/health/live")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "WorkshopPro"


def test_readiness_reports_failure_without_leaking_details(client: TestClient) -> None:
    client.app.dependency_overrides[get_db] = lambda: _BrokenSession()  # type: ignore[attr-defined]
    client.app.dependency_overrides[get_redis] = lambda: _OkRedis()  # type: ignore[attr-defined]

    res = client.get("/api/v1/health/ready")

    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "error"
    assert body["checks"]["database"]["status"] == "error"
    assert body["checks"]["database"]["detail"] == "unavailable"
    assert body["checks"]["redis"]["status"] == "ok"
    assert "secret" not in res.text


@pytest.mark.db
@pytest.mark.usefixtures("live_dependencies")
def test_readiness_against_real_dependencies(client: TestClient) -> None:
    res = client.get("/api/v1/health/ready")

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ok"
