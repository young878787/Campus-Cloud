"""審計日誌 schemas"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.audit_log import AuditAction


class AuditLogPublic(BaseModel):
    """公開的審計日誌"""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    user_full_name: str | None = None
    vmid: int | None
    action: AuditAction
    details: str
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogsPublic(BaseModel):
    """審計日誌列表"""

    data: list[AuditLogPublic]
    count: int
