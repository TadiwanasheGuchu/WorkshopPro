"""Inventory report permission for default roles

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-16 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ["administrator", "workshop_manager", "inventory_manager", "accounts"]


def upgrade() -> None:
    for template in ROLES:
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission) "
                "SELECT id, 'reports.inventory' FROM roles WHERE template_key = :template "
                "ON CONFLICT DO NOTHING"
            ).bindparams(template=template)
        )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission = 'reports.inventory'")
