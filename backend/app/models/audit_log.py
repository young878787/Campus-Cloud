"""審計日誌模型"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlmodel import Column, DateTime, Enum, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User


class AuditAction(str, enum.Enum):
    """審計操作類型"""

    # 規格調整
    spec_change_request = "spec_change_request"
    spec_change_apply = "spec_change_apply"

    # 快照管理
    snapshot_create = "snapshot_create"
    snapshot_delete = "snapshot_delete"
    snapshot_rollback = "snapshot_rollback"

    # 配置更新
    config_update = "config_update"

    # 資源創建
    vm_create = "vm_create"
    lxc_create = "lxc_create"

    # 資源控制
    resource_start = "resource_start"
    resource_stop = "resource_stop"
    resource_reboot = "resource_reboot"
    resource_shutdown = "resource_shutdown"
    resource_reset = "resource_reset"
    resource_delete = "resource_delete"

    # VM 申請
    vm_request_submit = "vm_request_submit"
    vm_request_review = "vm_request_review"
    ai_api_request_submit = "ai_api_request_submit"
    ai_api_request_review = "ai_api_request_review"

    # 用戶管理
    user_create = "user_create"
    user_update = "user_update"
    user_delete = "user_delete"

    # 群組管理
    group_create = "group_create"
    group_delete = "group_delete"
    group_member_add = "group_member_add"
    group_member_remove = "group_member_remove"
    batch_provision_vm = "batch_provision_vm"
    batch_provision_lxc = "batch_provision_lxc"

    # 腳本部署
    script_deploy = "script_deploy"


class AuditLog(SQLModel, table=True):
    """審計日誌表"""

    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        description="操作者ID",
    )
    vmid: int | None = Field(default=None, description="操作的VM/CT ID")
    action: AuditAction = Field(
        sa_column=Column(Enum(AuditAction), nullable=False), description="操作類型"
    )
    details: str = Field(description="操作詳情")
    ip_address: str | None = Field(default=None, description="操作來源IP")
    user_agent: str | None = Field(default=None, description="User Agent")
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="操作時間",
    )

    # Relationship
    user: Optional["User"] = Relationship(back_populates="audit_logs")


__all__ = [
    "AuditAction",
    "AuditLog",
]
