"""Installation and maintenance commands.

Usage:
    python -m app.cli create-organisation --name "Acme Motors" \\
        --owner-email owner@example.com --owner-name "Owner Name"

The owner's password is prompted for (or read from stdin with --password-stdin) and is
never accepted as a command-line argument, which would leave it in shell history.
"""

import argparse
import getpass
import sys

from pydantic import TypeAdapter, ValidationError

from app.core.errors import AppError
from app.db.session import get_sessionmaker
from app.schemas.branch import BranchCode
from app.schemas.common import Email, Password
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

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
