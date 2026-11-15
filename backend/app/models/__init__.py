"""ORM models.

Import every model module here so Alembic autogenerate sees all tables.
No business tables exist yet (Phase 0); Phase 1 adds identity and organisation models.
"""

from app.db.base import Base

__all__ = ["Base"]
