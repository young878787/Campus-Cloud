"""IP 分配記錄模型"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from .base import get_datetime_utc


class IpAllocation(SQLModel, table=True):
    """IP 分配記錄

    追蹤子網內每一個已分配的 IP 位址，確保不重複使用。
    purpose 欄位區分用途：vm, lxc, gateway_vm, pve_host, subnet_gateway, reserved。
    """

    __tablename__ = "ip_allocation"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ip_address: str = Field(max_length=50, unique=True, index=True)
    purpose: str = Field(max_length=30)
    vmid: int | None = Field(default=None, index=True)
    description: str | None = Field(default=None, max_length=255)
    allocated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )


__all__ = ["IpAllocation"]
