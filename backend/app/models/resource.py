"""資源模型"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Column, DateTime, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User


class Resource(SQLModel, table=True):
    """資源額外信息表，儲存VM/Container的環境類型、到期日等資訊."""

    __tablename__ = "resources"

    vmid: int = Field(primary_key=True, description="VM/Container ID")
    user_id: uuid.UUID = Field(foreign_key="user.id", description="擁有者ID")
    environment_type: str = Field(
        description="環境類型，例如：Web開發標準版、LLM微調環境等"
    )
    os_info: str | None = Field(default=None, description="作業系統資訊")
    expiry_date: date | None = Field(default=None, description="到期日，None表示無期限")
    template_id: int | None = Field(
        default=None, description="使用的模板ID（如果是從模板創建）"
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="創建時間",
    )

    # Relationship
    user: Optional["User"] = Relationship(back_populates="resources")


__all__ = [
    "Resource",
]
