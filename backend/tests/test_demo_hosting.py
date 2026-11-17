"""Pieces used by the free hosted demo: database storage, log-only email, hosted
database URLs, and the demo seed."""

from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.demo import DemoError, seed, staff_email
from app.integrations.email import LogEmailSender, OutgoingEmail
from app.integrations.storage import DatabaseStorage, StorageError
from app.models import JobCard
from app.services import backups


@pytest.mark.usefixtures("db")
def test_database_storage_round_trip() -> None:
    storage = DatabaseStorage()
    storage.put("org/a/photo.jpg", b"first", "image/jpeg")
    storage.put("org/a/photo.jpg", b"second", "image/png")  # overwrite, like S3
    storage.put("org/b/report.pdf", b"%PDF", "application/pdf")
    assert storage.get("org/a/photo.jpg") == b"second"
    assert storage.content_type("org/a/photo.jpg") == "image/png"
    assert list(storage.list_keys()) == ["org/a/photo.jpg", "org/b/report.pdf"]
    storage.delete("org/a/photo.jpg")
    with pytest.raises(StorageError):
        storage.get("org/a/photo.jpg")


def test_hosted_database_urls_use_psycopg() -> None:
    for url in ("postgres://u:p@db.example.com/app", "postgresql://u:p@db.example.com/app"):
        s = Settings(database_url=url)
        assert str(s.database_url).startswith("postgresql+psycopg://u:p@db.example.com")


def test_log_email_never_logs_body(caplog: Any) -> None:
    caplog.set_level("INFO")
    LogEmailSender().deliver(
        OutgoingEmail(to="someone@example.com", subject="Reset", text="secret-token-123")
    )
    assert "secret-token-123" not in caplog.text
    assert "someone@" not in caplog.text


def test_demo_modes_refused_in_production() -> None:
    s = Settings(environment="production", email_provider="log", storage_backend="database")
    assert any("EMAIL_PROVIDER=log" in p for p in s.production_problems())
    assert not any("STORAGE_ACCESS_KEY" in p for p in s.production_problems())


def test_seed_demo(app: Any, db: Session) -> None:
    password = "demo-password-2026"
    assert seed(db, app, password) == "Demo Motors (demo data)"
    statuses = set(db.scalars(select(JobCard.status)))
    assert {
        "completed",
        "ready_for_collection",
        "repair_in_progress",
        "awaiting_approval",
        "diagnosis_in_progress",
        "vehicle_received",
    } <= statuses
    assert backups.verify(db, DatabaseStorage()).ok
    with pytest.raises(DemoError):
        seed(db, app, password)
    names = db.execute(text("SELECT display_name FROM customers")).scalars().all()
    assert all("(demo)" in n for n in names)
    assert db.scalar(select(func.count()).select_from(JobCard)) == 6
    assert staff_email("owner").endswith("example.com")
