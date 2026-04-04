"""Proxmox 連線設定模型"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from .base import get_datetime_utc


class ProxmoxConfig(SQLModel, table=True):
    """Proxmox 連線設定（單列 singleton，id 固定為 1）"""

    __tablename__ = "proxmox_config"

    id: int = Field(default=1, primary_key=True)
    host: str = Field(max_length=255)
    user: str = Field(max_length=255)
    encrypted_password: str = Field(max_length=2048)
    verify_ssl: bool = Field(default=False)
    iso_storage: str = Field(default="local", max_length=255)
    data_storage: str = Field(default="local-lvm", max_length=255)
    api_timeout: int = Field(default=30)
    task_check_interval: int = Field(default=2)
    pool_name: str = Field(default="CampusCloud", max_length=255)
    ca_cert: str | None = Field(default=None, sa_type=sa.Text())
    gateway_ip: str | None = Field(default=None, max_length=255)
    local_subnet: str | None = Field(default=None, max_length=50)
    default_node: str | None = Field(default=None, max_length=255)
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )


__all__ = ["ProxmoxConfig"]
