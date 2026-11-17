"""Object bytes kept in PostgreSQL (STORAGE_BACKEND=database).

Infrastructure table, not a business record: it mirrors an S3 bucket. Keys are opaque and
every access goes through stored_files, which carries organisation_id and is permission
checked, so this table has no organisation_id of its own.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StoredObject(Base):
    __tablename__ = "stored_objects"

    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
