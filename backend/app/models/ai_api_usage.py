import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

from .base import get_datetime_utc

if TYPE_CHECKING:
    from .ai_api_credential import AIAPICredential
    from .user import User


class AIAPIUsage(SQLModel, table=True):
    """AI API 使用量记录表"""

    __tablename__ = "ai_api_usage"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    credential_id: uuid.UUID = Field(foreign_key="ai_api_credentials.id", index=True)
    model_name: str = Field(max_length=255)
    request_type: str = Field(max_length=50)  # chat_completion, completion, etc.
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    request_duration_ms: int | None = Field(default=None)
    status: str = Field(max_length=50)  # success, error
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
        index=True,
    )

    # 关系
    user: "User" = Relationship()
    credential: "AIAPICredential" = Relationship()


__all__ = ["AIAPIUsage"]
