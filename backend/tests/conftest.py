from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.redis import get_redis
from app.db.session import get_engine
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def live_dependencies() -> None:
    """Skip the test unless PostgreSQL and Redis from settings are reachable."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        get_redis().ping()
    except Exception as exc:
        pytest.skip(f"PostgreSQL/Redis not reachable: {type(exc).__name__}")
