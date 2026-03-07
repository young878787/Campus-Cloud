"""虛擬機申請 schemas"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.vm_request import VMRequestStatus


# ===== Request Schemas =====


class VMRequestCreate(BaseModel):
    """提交虛擬機申請"""

    reason: str = Field(min_length=10)
    resource_type: str  # "lxc" 或 "vm"
    hostname: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", max_length=63)
    cores: int = 2
    memory: int = 2048
    password: str = Field(min_length=8, max_length=128)
    storage: str = "local-lvm"
    os_info: str | None = None
    expiry_date: date | None = None

    # LXC 專用
    ostemplate: str | None = None
    rootfs_size: int | None = None

    # VM 專用
    template_id: int | None = None
    disk_size: int | None = None
    username: str | None = None


class VMRequestReview(BaseModel):
    """審核虛擬機申請"""

    status: VMRequestStatus
    review_comment: str | None = None


# ===== Response Schemas =====


class VMRequestPublic(BaseModel):
    """公開的虛擬機申請資訊"""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    user_full_name: str | None = None
    reason: str
    resource_type: str
    hostname: str
    cores: int
    memory: int
    storage: str
    environment_type: str
    os_info: str | None = None
    expiry_date: date | None = None

    # LXC 專用
    ostemplate: str | None = None
    rootfs_size: int | None = None

    # VM 專用
    template_id: int | None = None
    disk_size: int | None = None
    username: str | None = None

    # 審核狀態
    status: VMRequestStatus
    reviewer_id: uuid.UUID | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None
    vmid: int | None = None
    created_at: datetime


class VMRequestsPublic(BaseModel):
    """虛擬機申請列表"""

    data: list[VMRequestPublic]
    count: int
