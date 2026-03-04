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
    from .machine import Resource
    from .spec_change_request import SpecChangeRequest
    from .vm_request import VMRequest


# Shared properties
class UserBase(SQLModel):
    """使用者基礎屬性"""

    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    """建立使用者時接收的資料"""

    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    """使用者自行註冊時使用的資料"""

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    """更新使用者時接收的資料"""

    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    """使用者更新自己資料時使用"""

    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    """更新密碼請求"""

    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


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


# Properties to return via API, id is always required
class UserPublic(UserBase):
    """API 回傳的使用者資料"""

    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    """API 回傳的使用者列表"""

    data: list[UserPublic]
    count: int


__all__ = [
    "UserBase",
    "UserCreate",
    "UserRegister",
    "UserUpdate",
    "UserUpdateMe",
    "UpdatePassword",
    "User",
    "UserPublic",
    "UsersPublic",
]
