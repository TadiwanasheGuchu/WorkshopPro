"""Installation and maintenance commands.

Usage:
    python -m app.cli create-organisation --name "Acme Motors" \\
        --owner-email owner@example.com --owner-name "Owner Name"
    python -m app.cli backup-manifest > manifest.json
    python -m app.cli storage-export > objects.tar
    python -m app.cli storage-import < objects.tar
    python -m app.cli verify-restore --manifest - < manifest.json
    DEMO_PASSWORD=... python -m app.cli seed-demo [--if-empty]

The backup commands stream through stdin/stdout so they can run inside the backend
container (`docker compose exec -T backend ...`); see infrastructure/backups/.

The owner's password is prompted for (or read from stdin with --password-stdin) and is
never accepted as a command-line argument, which would leave it in shell history.
"""

import argparse
import getpass
import json
import sys

from pydantic import TypeAdapter, ValidationError

from app.core.errors import AppError
from app.db.session import get_sessionmaker
from app.integrations.storage import get_storage
from app.schemas.branch import BranchCode
from app.schemas.common import Email, Password
from app.services import backups
from app.services.organisations import create_organisation


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Owner password: ")
    if getpass.getpass("Repeat password: ") != first:
        raise SystemExit("Passwords do not match.")
    return first


def _create_organisation(args: argparse.Namespace) -> int:
    try:
        email = TypeAdapter(Email).validate_python(args.owner_email)
        branch_code = TypeAdapter(BranchCode).validate_python(args.branch_code)
        password = TypeAdapter(Password).validate_python(_read_password(args.password_stdin))
    except ValidationError as exc:
        print(f"Invalid input: {exc.errors()[0]['msg']}", file=sys.stderr)
        return 2

    with get_sessionmaker()() as db:
        try:
            result = create_organisation(
                db,
                name=args.name.strip(),
                owner_email=email,
                owner_name=args.owner_name.strip(),
                owner_password=password,
                branch_name=args.branch_name.strip(),
                branch_code=branch_code,
            )
        except AppError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            return 1
    print(f"Created organisation '{result.organisation.name}' ({result.organisation.id}).")
    print(f"Owner {result.owner.email} can now sign in.")
    return 0


def _backup_manifest(args: argparse.Namespace) -> int:
    snapshot = json.load(sys.stdin) if args.snapshot_stdin else None
    with get_sessionmaker()() as db:
        print(json.dumps(backups.manifest(db, get_storage(), snapshot), indent=2))
    return 0


def _storage_export(_args: argparse.Namespace) -> int:
    count = backups.export_objects(get_storage(), sys.stdout.buffer)
    sys.stdout.buffer.flush()
    print(f"Exported {count} objects.", file=sys.stderr)
    return 0


def _storage_import(_args: argparse.Namespace) -> int:
    count = backups.import_objects(get_storage(), sys.stdin.buffer)
    print(f"Imported {count} objects.", file=sys.stderr)
    return 0


def _verify_restore(args: argparse.Namespace) -> int:
    expected = None
    if args.manifest:
        source = sys.stdin if args.manifest == "-" else open(args.manifest)  # noqa: SIM115
        with source:
            expected = json.load(source)
    with get_sessionmaker()() as db:
        result = backups.verify(db, get_storage(), expected)
    print(backups.verification_json(result))
    return 0 if result.ok else 1


def _seed_demo(args: argparse.Namespace) -> int:
    import os

    from app.db.session import get_sessionmaker as sessionmaker
    from app.demo import STAFF, DemoError, seed, staff_email
    from app.main import create_app
    from app.models import Organisation

    password = os.environ.get("DEMO_PASSWORD", "")
    try:
        TypeAdapter(Password).validate_python(password)
    except ValidationError:
        print("Set DEMO_PASSWORD to a valid password (see the sign-in rules).", file=sys.stderr)
        return 2
    with sessionmaker()() as db:
        if args.if_empty and db.query(Organisation.id).first() is not None:
            print("Database already has an organisation; demo not seeded.", file=sys.stderr)
            return 0
        try:
            name = seed(db, create_app(), password)
        except DemoError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    print(f"Seeded '{name}'. Sign in as any of (password from DEMO_PASSWORD):")
    for handle, full_name, _role in STAFF:
        print(f"  {staff_email(handle):40} {full_name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="WorkshopPro admin")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-organisation", help="Create an organisation and its owner")
    create.add_argument("--name", required=True, help="Trading name of the workshop")
    create.add_argument("--owner-email", required=True)
    create.add_argument("--owner-name", required=True)
    create.add_argument("--branch-name", default="Main branch")
    create.add_argument("--branch-code", default="MAIN")
    create.add_argument(
        "--password-stdin", action="store_true", help="Read the owner password from stdin"
    )
    create.set_defaults(handler=_create_organisation)

    man = sub.add_parser(
        "backup-manifest", help="Print row counts, schema revision and object count as JSON"
    )
    man.add_argument(
        "--snapshot-stdin",
        action="store_true",
        help="Read {alembic_revision, tables} taken in the pg_dump snapshot from stdin",
    )
    man.set_defaults(handler=_backup_manifest)
    sub.add_parser(
        "storage-export", help="Write every object in storage to stdout as a tar stream"
    ).set_defaults(handler=_storage_export)
    sub.add_parser(
        "storage-import", help="Read a tar stream from stdin into object storage"
    ).set_defaults(handler=_storage_import)
    verify = sub.add_parser(
        "verify-restore", help="Check counts, ledgers, balances and files after a restore"
    )
    verify.add_argument("--manifest", help="Backup manifest JSON file, or - for stdin")
    verify.set_defaults(handler=_verify_restore)

    demo = sub.add_parser(
        "seed-demo", help="Create the demo organisation (password from DEMO_PASSWORD)"
    )
    demo.add_argument(
        "--if-empty", action="store_true", help="Do nothing if any organisation exists"
    )
    demo.set_defaults(handler=_seed_demo)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
