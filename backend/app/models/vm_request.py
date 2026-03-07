"""虛擬機申請相關模型"""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Column, DateTime, Enum, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User


class VMRequestStatus(str, enum.Enum):
    """虛擬機申請狀態"""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class VMRequest(SQLModel, table=True):
    """虛擬機申請表，儲存使用者申請虛擬機的資訊與審核狀態."""

    __tablename__ = "vm_requests"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", description="申請者ID")

    # 申請原因
    reason: str = Field(description="申請原因")

    # 資源類型: lxc 或 vm
    resource_type: str = Field(description="資源類型: lxc 或 vm")

    # 共用欄位
    hostname: str = Field(description="主機名稱")
    cores: int = Field(default=2, description="CPU 核心數")
    memory: int = Field(default=2048, description="記憶體 (MB)")
    password: str = Field(description="密碼")
    storage: str = Field(default="local-lvm", description="儲存位置")
    environment_type: str = Field(default="自訂規格", description="環境類型")
    os_info: str | None = Field(default=None, description="作業系統資訊")
    expiry_date: date | None = Field(default=None, description="到期日")

    # LXC 專用
    ostemplate: str | None = Field(default=None, description="LXC 作業系統模板")
    rootfs_size: int | None = Field(default=None, description="LXC 磁碟大小 (GB)")
    unprivileged: bool = Field(default=True, description="LXC 非特權模式")

    # VM 專用
    template_id: int | None = Field(default=None, description="VM 模板 ID")
    disk_size: int | None = Field(default=None, description="VM 磁碟大小 (GB)")
    username: str | None = Field(default=None, description="VM 使用者名稱")

    # 審核狀態
    status: VMRequestStatus = Field(
        default=VMRequestStatus.pending,
        sa_column=Column(Enum(VMRequestStatus), nullable=False, default="pending"),
        description="審核狀態",
    )
    reviewer_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", description="審核者ID"
    )
    review_comment: str | None = Field(default=None, description="審核備註")
    reviewed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="審核時間",
    )

    # 建立後的 VMID（審核通過並建立後填入）
    vmid: int | None = Field(default=None, description="建立後的 VM/Container ID")

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="申請時間",
    )

    # Relationships
    user: Optional["User"] = Relationship(
        back_populates="vm_requests",
        sa_relationship_kwargs={"foreign_keys": "[VMRequest.user_id]"},
    )
    reviewer: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[VMRequest.reviewer_id]"},
    )


__all__ = [
    "VMRequestStatus",
    "VMRequest",
]
