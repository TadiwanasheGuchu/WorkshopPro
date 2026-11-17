"""Invoice list index matching the list sort order (performance review)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-17 19:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index('ix_invoices_org_status', table_name='invoices')
    op.create_index(
        'ix_invoices_list',
        'invoices',
        ['organisation_id', 'status', sa.text('issue_date DESC NULLS FIRST'), 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_invoices_list', table_name='invoices')
    op.create_index('ix_invoices_org_status', 'invoices', ['organisation_id', 'status', 'issue_date'])
