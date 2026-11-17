"""Backup support: object storage export/import, a manifest, and post-restore checks.

The database itself is dumped with pg_dump by infrastructure/backups/backup.sh. This
module covers what pg_dump cannot: the photos and documents in object storage (exported
through the S3 API, so it works for SeaweedFS and managed S3 alike) and a verification
that a restored installation is complete and internally consistent.
"""

import io
import json
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import IO, Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.integrations.storage import ObjectStorage
from app.models import Base
from app.models.inspection import StoredFile

MANIFEST_FORMAT = 1
CONTENT_TYPE_HEADER = "WORKSHOPPRO.content_type"


def export_objects(storage: ObjectStorage, out: IO[bytes]) -> int:
    """Write every stored object to a tar stream. Returns the number of objects."""
    count = 0
    with tarfile.open(fileobj=out, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        for key in storage.list_keys():
            data = storage.get(key)
            info = tarfile.TarInfo(name=key)
            info.size = len(data)
            info.mtime = int(datetime.now(UTC).timestamp())
            info.pax_headers = {CONTENT_TYPE_HEADER: storage.content_type(key)}
            tar.addfile(info, io.BytesIO(data))
            count += 1
    return count


def import_objects(storage: ObjectStorage, source: IO[bytes]) -> int:
    """Put every object from a tar stream written by export_objects. Existing keys are
    overwritten with the backed-up bytes. Returns the number of objects."""
    count = 0
    with tarfile.open(fileobj=source, mode="r|") as tar:
        for member in tar:
            if not member.isfile() or member.name.startswith("/") or ".." in member.name:
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            content_type = member.pax_headers.get(CONTENT_TYPE_HEADER, "application/octet-stream")
            storage.put(member.name, handle.read(), content_type)
            count += 1
    return count


def _revision(db: Session) -> str | None:
    return db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


def table_counts(db: Session) -> dict[str, int]:
    return {
        t.name: int(db.execute(select(func.count()).select_from(t)).scalar_one())
        for t in Base.metadata.sorted_tables
    }


def manifest(
    db: Session, storage: ObjectStorage, snapshot: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Describe a backup. `snapshot` holds the schema revision and row counts read in the
    same database snapshot as pg_dump (backup.sh), so they describe exactly the dump;
    without it they are read now."""
    return {
        "format": MANIFEST_FORMAT,
        "created_at": datetime.now(UTC).isoformat(),
        "alembic_revision": snapshot["alembic_revision"] if snapshot else _revision(db),
        "tables": snapshot["tables"] if snapshot else table_counts(db),
        "objects": sum(1 for _ in storage.list_keys()),
    }


@dataclass
class Verification:
    checks: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def check(self, name: str, failures: list[str]) -> None:
        self.checks.append(name)
        self.problems.extend(f"{name}: {f}" for f in failures)


# Each query returns rows that violate an invariant; an empty result means consistent.
_CONSISTENCY_SQL = {
    "stock on hand equals the movement ledger": """
        SELECT l.part_id, l.location_id, l.on_hand, COALESCE(m.total, 0)
        FROM stock_levels l
        LEFT JOIN (SELECT part_id, location_id, SUM(quantity) AS total
                   FROM stock_movements GROUP BY part_id, location_id) m
          ON m.part_id = l.part_id AND m.location_id = l.location_id
        WHERE l.on_hand <> COALESCE(m.total, 0)
        UNION ALL
        SELECT m.part_id, m.location_id, NULL, SUM(m.quantity)
        FROM stock_movements m
        LEFT JOIN stock_levels l ON l.part_id = m.part_id AND l.location_id = m.location_id
        WHERE l.part_id IS NULL
        GROUP BY m.part_id, m.location_id
    """,
    "reserved stock equals open reservations": """
        SELECT l.part_id, l.location_id, l.reserved, COALESCE(r.outstanding, 0)
        FROM stock_levels l
        LEFT JOIN (SELECT part_id, location_id,
                          SUM(quantity - issued_quantity - released_quantity) AS outstanding
                   FROM stock_reservations WHERE status = 'open'
                   GROUP BY part_id, location_id) r
          ON r.part_id = l.part_id AND r.location_id = l.location_id
        WHERE l.reserved <> COALESCE(r.outstanding, 0)
    """,
    "invoice amount paid equals payment allocations": """
        SELECT i.id, i.amount_paid, COALESCE(a.total, 0)
        FROM invoices i
        LEFT JOIN (SELECT invoice_id, SUM(amount) AS total
                   FROM payment_allocations GROUP BY invoice_id) a ON a.invoice_id = i.id
        WHERE i.amount_paid <> COALESCE(a.total, 0)
    """,
    "invoice amount credited equals credit notes": """
        SELECT i.id, i.amount_credited, COALESCE(c.total, 0)
        FROM invoices i
        LEFT JOIN (SELECT invoice_id, SUM(total) AS total
                   FROM credit_notes GROUP BY invoice_id) c ON c.invoice_id = i.id
        WHERE i.amount_credited <> COALESCE(c.total, 0)
    """,
}


def verify(
    db: Session, storage: ObjectStorage, expected: dict[str, Any] | None = None
) -> Verification:
    """Check a (restored) installation: row counts against the backup manifest, ledger
    and balance invariants, and that every stored file's bytes are present."""
    result = Verification()

    if expected is not None:
        revision = _revision(db)
        if expected.get("alembic_revision") != revision:
            # Migrations ran after the restore; data migrations may legitimately add rows.
            result.warnings.append(
                f"backup is from revision {expected.get('alembic_revision')}, database is now "
                f"at {revision}; row counts compared for tables present in both"
            )
        counts = table_counts(db)
        mismatches = []
        for table, want in sorted(expected.get("tables", {}).items()):
            have = counts.get(table)
            if have is None:
                mismatches.append(f"table {table} is missing")
            elif have < want or (have != want and expected.get("alembic_revision") == revision):
                mismatches.append(f"{table} has {have} rows, backup had {want}")
        result.check("row counts match the backup", mismatches)

    for name, sql in _CONSISTENCY_SQL.items():
        rows = db.execute(text(sql)).all()
        result.check(name, [", ".join(str(v) for v in row) for row in rows[:20]])

    present = set(storage.list_keys())
    missing = []
    for key, thumb in db.execute(select(StoredFile.storage_key, StoredFile.thumbnail_key)):
        missing += [k for k in (key, thumb) if k and k not in present]
    result.check("every stored file is in object storage", missing[:20])

    if expected is not None and len(present) < int(expected.get("objects", 0)):
        result.problems.append(
            f"object storage has {len(present)} objects, backup had {expected['objects']}"
        )
    return result


def verification_json(result: Verification) -> str:
    return json.dumps(
        {
            "ok": result.ok,
            "checks": result.checks,
            "problems": result.problems,
            "warnings": result.warnings,
        },
        indent=2,
    )
