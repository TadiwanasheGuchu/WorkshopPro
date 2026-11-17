"""Object bytes in PostgreSQL for STORAGE_BACKEND=database (hosted demo)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-18 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'stored_objects',
        sa.Column('key', sa.String(length=300), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key', name=op.f('pk_stored_objects')),
    )


def downgrade() -> None:
    op.drop_table('stored_objects')
