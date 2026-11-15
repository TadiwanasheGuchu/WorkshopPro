"""Baseline: enable required PostgreSQL extensions.

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # citext: case-insensitive emails and registration numbers (Phase 1+).
    # pg_trgm: fast partial search on customer names, registrations, VINs (Phase 2).
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS citext")
