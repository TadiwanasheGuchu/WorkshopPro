"""Database engine and request-scoped sessions."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        connect_args={"connect_timeout": 5},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session.

    Services own transaction boundaries (`with db.begin(): ...`); this dependency
    only guarantees the session is closed and uncommitted work is rolled back.
    """
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
