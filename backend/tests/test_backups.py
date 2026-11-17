"""Backup tooling: object export/import round trip and post-restore verification."""

import io
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cli
from app.integrations.storage import InMemoryStorage
from app.models.inspection import StoredFile
from app.services import backups
from tests.conftest import Api, OrgFixture
from tests.test_inventory import _adjust, _main, _part


def test_objects_round_trip() -> None:
    source = InMemoryStorage()
    source.put("org/a/photo.jpg", b"\xff\xd8jpeg bytes", "image/jpeg")
    source.put("org/a/photo-thumb.jpg", b"thumb", "image/jpeg")
    source.put("org/b/report.pdf", b"%PDF-1.7", "application/pdf")
    buf = io.BytesIO()
    assert backups.export_objects(source, buf) == 3

    target = InMemoryStorage()
    target.put("org/a/photo.jpg", b"stale", "image/jpeg")
    buf.seek(0)
    assert backups.import_objects(target, buf) == 3
    assert target.objects == source.objects


def _stock(owner_api: Api) -> dict[str, Any]:
    part = _part(owner_api)
    loc = _main(owner_api)
    _adjust(owner_api, loc["id"], [{"part_id": part["id"], "counted": "5"}])
    return {"part": part["id"], "loc": loc["id"]}


def _file(org: OrgFixture, key: str) -> None:
    org.db.add(
        StoredFile(
            organisation_id=org.id,
            purpose="inspection_photo",
            storage_key=key,
            content_type="image/jpeg",
            size_bytes=4,
            sha256="0" * 64,
        )
    )
    org.db.commit()


def test_verify_passes_on_a_consistent_installation(
    owner_api: Api, org: OrgFixture, db: Session, storage: InMemoryStorage
) -> None:
    _stock(owner_api)
    _file(org, "org/photo.jpg")
    storage.put("org/photo.jpg", b"jpeg", "image/jpeg")

    expected = backups.manifest(db, storage)
    assert expected["tables"]["stock_movements"] == 1
    assert expected["objects"] == 1
    result = backups.verify(db, storage, expected)
    assert result.ok, result.problems
    assert len(result.checks) == 6


def test_verify_reports_problems(
    owner_api: Api, org: OrgFixture, db: Session, storage: InMemoryStorage
) -> None:
    ids = _stock(owner_api)
    _file(org, "org/missing.jpg")
    expected = backups.manifest(db, storage)
    expected["tables"]["customers"] = 7  # rows that did not come back
    expected["objects"] = 3

    # Force the running balance away from the ledger, as a damaged restore might.
    db.execute(text("SELECT set_config('workshoppro.stock_ledger', 'on', true)"))
    db.execute(
        text("UPDATE stock_levels SET on_hand = 9 WHERE part_id = :part AND location_id = :loc"),
        ids,
    )
    result = backups.verify(db, storage, expected)
    db.rollback()

    problems = "\n".join(result.problems)
    assert not result.ok
    assert "customers has 0 rows, backup had 7" in problems
    assert "stock on hand equals the movement ledger" in problems
    assert "org/missing.jpg" in problems
    assert "object storage has 0 objects, backup had 3" in problems


def test_cli_verify_exit_code(
    db: Session, storage: InMemoryStorage, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cli, "get_storage", lambda: storage)
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: lambda: db)
    assert cli.main(["verify-restore"]) == 0
    assert '"ok": true' in capsys.readouterr().out
