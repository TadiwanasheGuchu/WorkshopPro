"""Test configuration.

Tests run against a real PostgreSQL database (`<db>_test`, created and migrated
automatically) and Redis database 15. Tables are truncated between tests.
Set TEST_DATABASE_URL / TEST_REDIS_URL to override.
"""

import os
from urllib.parse import urlsplit, urlunsplit

_base_db = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://workshoppro:workshoppro@localhost:5432/workshoppro"
)
_parts = urlsplit(_base_db)
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", urlunsplit(_parts._replace(path=_parts.path.rstrip("/") + "_test"))
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
os.environ["ENVIRONMENT"] = "test"
os.environ["APP_BASE_URL"] = "http://testserver"
# Background tasks run in-process so tests see their effects immediately.
os.environ["CELERY_EAGER"] = "true"

import uuid  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from httpx import Response  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.core.security import CSRF_COOKIE, hash_password  # noqa: E402
from app.core.time import utcnow  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.integrations.email import InMemoryEmailSender, get_email_sender  # noqa: E402
from app.integrations.storage import InMemoryStorage, get_storage  # noqa: E402
from app.integrations.whatsapp import LogWhatsAppSender, get_whatsapp_sender  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Branch, Role, User, UserRoleAssignment  # noqa: E402
from app.services import notifications  # noqa: E402
from app.services.organisations import create_organisation  # noqa: E402

PASSWORD = "correct-horse-battery"


def _ensure_database() -> bool:
    url = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except Exception:
        return False
    finally:
        admin.dispose()
    return True


@pytest.fixture(scope="session")
def _database() -> Iterator[None]:
    if not _ensure_database():
        pytest.skip("PostgreSQL not reachable")
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    command.upgrade(cfg, "head")
    yield
    get_engine().dispose()


@pytest.fixture
def db(_database: None) -> Iterator[Session]:
    engine = get_engine()
    with engine.begin() as conn:
        tables = conn.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        ).all()
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    try:
        get_redis().flushdb()
    except Exception:
        pytest.skip("Redis not reachable")
    session = get_sessionmaker()()
    yield session
    session.close()


@pytest.fixture
def outbox() -> InMemoryEmailSender:
    return InMemoryEmailSender()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def whatsapp() -> LogWhatsAppSender:
    return LogWhatsAppSender()


@pytest.fixture
def app(
    outbox: InMemoryEmailSender, storage: InMemoryStorage, whatsapp: LogWhatsAppSender
) -> Iterator[Any]:
    application = create_app()
    application.dependency_overrides[get_email_sender] = lambda: outbox
    application.dependency_overrides[get_storage] = lambda: storage
    # The notification worker resolves senders itself; point it at the same fakes.
    notifications.senders.email = lambda: outbox
    notifications.senders.whatsapp = lambda: whatsapp
    yield application
    application.dependency_overrides.clear()
    notifications.senders.email = get_email_sender
    notifications.senders.whatsapp = get_whatsapp_sender


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class Api:
    """TestClient wrapper that behaves like the frontend: keeps cookies and sends the
    CSRF header on unsafe requests."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def csrf(self) -> str:
        token = self.client.cookies.get(CSRF_COOKIE)
        if not token:
            token = self.client.get("/api/v1/auth/csrf").json()["csrf_token"]
        return token

    def request(self, method: str, path: str, **kwargs: Any) -> Response:
        headers = kwargs.pop("headers", {}) or {}
        if method.upper() not in ("GET", "HEAD", "OPTIONS"):
            headers.setdefault("X-CSRF-Token", self.csrf())
        return self.client.request(method, f"/api/v1{path}", headers=headers, **kwargs)

    def get(self, path: str, **kw: Any) -> Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Response:
        return self.request("POST", path, **kw)

    def patch(self, path: str, **kw: Any) -> Response:
        return self.request("PATCH", path, **kw)

    def put(self, path: str, **kw: Any) -> Response:
        return self.request("PUT", path, **kw)

    def delete(self, path: str, **kw: Any) -> Response:
        return self.request("DELETE", path, **kw)

    def login(self, email: str, password: str = PASSWORD) -> Response:
        return self.post("/auth/login", json={"email": email, "password": password})


@pytest.fixture
def new_api(app: Any) -> Iterator[Any]:
    """Factory for independent API clients (separate cookie jars = separate users)."""
    clients: list[TestClient] = []

    def make() -> Api:
        c = TestClient(app, raise_server_exceptions=False)
        c.__enter__()
        clients.append(c)
        return Api(c)

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@dataclass
class OrgFixture:
    id: uuid.UUID
    owner_email: str
    branch_id: uuid.UUID
    db: Session

    def role(self, template_key: str) -> Role:
        return self.db.scalars(
            select(Role).where(Role.organisation_id == self.id, Role.template_key == template_key)
        ).one()

    def add_branch(self, code: str, name: str | None = None) -> Branch:
        from app.services.branches import create_branch_record

        branch = create_branch_record(self.db, self.id, name=name or f"Branch {code}", code=code)
        self.db.commit()
        return branch

    def add_user(
        self,
        email: str,
        roles: list[tuple[Role, uuid.UUID | None]],
        *,
        password: str | None = PASSWORD,
        is_active: bool = True,
    ) -> User:
        now = utcnow()
        user = User(
            organisation_id=self.id,
            email=email,
            full_name=email.split("@")[0].title(),
            password_hash=hash_password(password) if password else None,
            is_active=is_active,
            activated_at=now if password else None,
            invited_at=now,
        )
        self.db.add(user)
        self.db.flush()
        for role, branch_id in roles:
            self.db.add(
                UserRoleAssignment(
                    organisation_id=self.id, user_id=user.id, role_id=role.id, branch_id=branch_id
                )
            )
        self.db.commit()
        return user


@pytest.fixture
def make_org(db: Session) -> Any:
    def make(name: str = "Kalahari Motors", owner_email: str | None = None) -> OrgFixture:
        email = owner_email or f"owner-{uuid.uuid4().hex[:6]}@example.com"
        result = create_organisation(
            db, name=name, owner_email=email, owner_name="Olivia Owner", owner_password=PASSWORD
        )
        branch_id = db.scalars(
            select(Branch.id).where(Branch.organisation_id == result.organisation.id)
        ).one()
        return OrgFixture(id=result.organisation.id, owner_email=email, branch_id=branch_id, db=db)

    return make


@pytest.fixture
def org(make_org: Any) -> OrgFixture:
    return make_org()


@pytest.fixture
def owner_api(org: OrgFixture, new_api: Any) -> Api:
    api = new_api()
    assert api.login(org.owner_email).status_code == 204
    return api


@pytest.fixture
def settings_override() -> Iterator[Any]:
    """Temporarily change settings values: settings_override(login_attempts_per_email=2)."""
    settings = get_settings()
    original: dict[str, Any] = {}

    def apply(**values: Any) -> None:
        for key, value in values.items():
            original.setdefault(key, getattr(settings, key))
            setattr(settings, key, value)

    yield apply
    for key, value in original.items():
        setattr(settings, key, value)


@pytest.fixture(scope="session")
def live_dependencies(_database: None) -> None:
    try:
        get_redis().ping()
    except Exception as exc:
        pytest.skip(f"Redis not reachable: {type(exc).__name__}")
