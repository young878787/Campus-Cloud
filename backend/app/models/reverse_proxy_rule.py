"""反向代理規則模型 — Traefik domain → VM 映射"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from .base import get_datetime_utc


class ReverseProxyRule(SQLModel, table=True):
    """儲存反向代理規則（domain → VM IP:port）。
    Campus Cloud 從此表生成 Traefik dynamic config。
    未來可擴展 dns_provider 欄位對接 Cloudflare 等 DNS API。
    """

    __tablename__ = "reverse_proxy_rule"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # VM 資訊
    vmid: int = Field(index=True, description="目標 VM ID")
    vm_ip: str = Field(max_length=64, description="目標 VM 內網 IP")

    # 網域對應
    domain: str = Field(
        max_length=255,
        sa_column_kwargs={"unique": True},
        description="對外網域名稱（如 mysite.campus.edu）",
    )
    zone_id: str | None = Field(default=None, max_length=64, description="Cloudflare Zone ID")
    cloudflare_record_id: str | None = Field(
        default=None,
        max_length=64,
        description="由 Campus Cloud 自動管理的 Cloudflare DNS record ID",
    )
    internal_port: int = Field(ge=1, le=65535, description="VM 內部 port")
    enable_https: bool = Field(default=True, description="是否啟用 HTTPS（Let's Encrypt）")

    # 預留 DNS provider 欄位（未來 Cloudflare 對接用）
    dns_provider: str = Field(
        default="manual",
        max_length=32,
        description="DNS 管理方式：manual / cloudflare / ...",
    )

    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=sa.DateTime(timezone=True),
    )


__all__ = ["ReverseProxyRule"]
