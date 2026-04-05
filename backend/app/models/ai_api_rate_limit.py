import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from .base import get_datetime_utc


class AIAPIRateLimit(SQLModel, table=True):
    """AI API 速率限制记录表"""

    __tablename__ = "ai_api_rate_limit"

    user_id: uuid.UUID = Field(foreign_key="user.id", primary_key=True)
    minute_key: str = Field(
        max_length=20, primary_key=True
    )  # 格式: "2026-04-01-10-30"
    request_count: int = Field(default=0)
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
        index=True,
    )


__all__ = ["AIAPIRateLimit"]
