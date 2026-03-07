"""使用者相關模型"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

from .base import get_datetime_utc

if TYPE_CHECKING:
    from .audit_log import AuditLog
    from .resource import Resource
    from .spec_change_request import SpecChangeRequest
    from .vm_request import VMRequest


# Shared properties
class UserBase(SQLModel):
    """使用者基礎屬性"""

    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    """使用者資料庫模型"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )

    # Relationships
    resources: list["Resource"] = Relationship(back_populates="user")
    vm_requests: list["VMRequest"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[VMRequest.user_id]"},
    )
    spec_change_requests: list["SpecChangeRequest"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[SpecChangeRequest.user_id]"},
    )
    audit_logs: list["AuditLog"] = Relationship(back_populates="user")


__all__ = [
    "UserBase",
    "User",
]
