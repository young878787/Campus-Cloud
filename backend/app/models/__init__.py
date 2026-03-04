"""
Models 模組

此模組包含所有資料模型定義：
- User 相關模型
- Item 相關模型
- Token 與通用模型

所有模型均從此處匯出，保持向後相容性。
"""

from sqlmodel import SQLModel

from .base import get_datetime_utc
from .machine import (
    LXCCreateResponse,
    LXCCreateSchema,
    NextVMIDSchema,
    NodeSchema,
    Resource,
    ResourcePublic,
    TemplateSchema,
    TerminalInfoSchema,
    VMCreateResponse,
    VMCreateSchema,
    VMSchema,
    VMTemplateSchema,
    VNCInfoSchema,
)
from .token import (
    Message,
    NewPassword,
    Token,
    TokenPayload,
)
from .vm_request import (
    VMRequest,
    VMRequestCreate,
    VMRequestPublic,
    VMRequestReview,
    VMRequestStatus,
    VMRequestsPublic,
)
from .user import (
    UpdatePassword,
    User,
    UserBase,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)
from .audit_log import (
    AuditAction,
    AuditLog,
    AuditLogPublic,
    AuditLogsPublic,
)
from .spec_change_request import (
    SpecChangeRequest,
    SpecChangeRequestCreate,
    SpecChangeRequestPublic,
    SpecChangeRequestReview,
    SpecChangeRequestsPublic,
    SpecChangeRequestStatus,
    SpecChangeType,
)

__all__ = [
    # Base
    "SQLModel",
    "get_datetime_utc",
    # User models
    "UserBase",
    "UserCreate",
    "UserRegister",
    "UserUpdate",
    "UserUpdateMe",
    "UpdatePassword",
    "User",
    "UserPublic",
    "UsersPublic",
    # Machine models
    "NodeSchema",
    "VMSchema",
    "VNCInfoSchema",
    "TerminalInfoSchema",
    "TemplateSchema",
    "VMTemplateSchema",
    "NextVMIDSchema",
    "LXCCreateSchema",
    "LXCCreateResponse",
    "Resource",
    "ResourcePublic",
    "VMCreateSchema",
    "VMCreateResponse",
    # Token & common models
    "Message",
    "Token",
    "TokenPayload",
    "NewPassword",
    # VM Request models
    "VMRequest",
    "VMRequestCreate",
    "VMRequestPublic",
    "VMRequestReview",
    "VMRequestStatus",
    "VMRequestsPublic",
    # Audit Log models
    "AuditAction",
    "AuditLog",
    "AuditLogPublic",
    "AuditLogsPublic",
    # Spec Change Request models
    "SpecChangeRequest",
    "SpecChangeRequestCreate",
    "SpecChangeRequestPublic",
    "SpecChangeRequestReview",
    "SpecChangeRequestsPublic",
    "SpecChangeRequestStatus",
    "SpecChangeType",
]
