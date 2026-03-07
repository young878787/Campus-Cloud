"""
Models 模組

此模組包含所有資料庫模型定義（DB tables + enums）。
API schemas 已移至 app.schemas 模組。
"""

from sqlmodel import SQLModel

from .base import get_datetime_utc
from .resource import Resource
from .user import User, UserBase
from .vm_request import VMRequest, VMRequestStatus
from .audit_log import AuditAction, AuditLog
from .spec_change_request import (
    SpecChangeRequest,
    SpecChangeRequestStatus,
    SpecChangeType,
)

__all__ = [
    # Base
    "SQLModel",
    "get_datetime_utc",
    # User
    "UserBase",
    "User",
    # Resource
    "Resource",
    # VM Request
    "VMRequest",
    "VMRequestStatus",
    # Audit Log
    "AuditAction",
    "AuditLog",
    # Spec Change Request
    "SpecChangeRequest",
    "SpecChangeRequestStatus",
    "SpecChangeType",
]
