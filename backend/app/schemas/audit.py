import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: str
    changes: dict[str, Any] | None
    actor_type: str
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    branch_id: uuid.UUID | None
    branch_name: str | None
    ip_address: str | None
    request_id: str | None
