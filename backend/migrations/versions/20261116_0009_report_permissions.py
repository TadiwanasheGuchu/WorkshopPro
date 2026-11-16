"""Report permissions for default roles

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-16 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODES = ["reports.operational", "reports.financial"]

GRANTS: dict[str, list[str]] = {
    "administrator": _CODES,
    "workshop_manager": _CODES,
    "accounts": ["reports.financial"],
}


def upgrade() -> None:
    for template, permissions in GRANTS.items():
        for permission in permissions:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission) "
                    "SELECT id, :permission FROM roles WHERE template_key = :template "
                    "ON CONFLICT DO NOTHING"
                ).bindparams(permission=permission, template=template)
            )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM role_permissions WHERE permission = ANY(:codes)").bindparams(
            codes=_CODES
        )
    )
