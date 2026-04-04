"""Proxmox 設定相關 schemas"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProxmoxConfigPublic(BaseModel):
    """回傳給前端的 Proxmox 設定（不含密碼與憑證原文）"""

    host: str
    user: str
    verify_ssl: bool
    iso_storage: str
    data_storage: str
    api_timeout: int
    task_check_interval: int
    pool_name: str
    gateway_ip: str | None = None  # 可能尚未設定（舊資料相容）
    local_subnet: str | None = None
    default_node: str | None = None
    updated_at: datetime | None = None
    is_configured: bool
    has_ca_cert: bool
    ca_fingerprint: str | None = None  # SHA-256 指紋，供前端顯示確認


class ProxmoxConfigUpdate(BaseModel):
    """更新 Proxmox 設定的請求 schema"""

    host: str
    user: str
    password: str | None = None  # None 表示不更新密碼
    verify_ssl: bool = False
    iso_storage: str = "local"
    data_storage: str = "local-lvm"
    api_timeout: int = Field(default=30, ge=1, le=300)
    task_check_interval: int = Field(default=2, ge=1, le=60)
    pool_name: str = "CampusCloud"
    ca_cert: str | None = None  # None 表示不更新；空字串表示清除
    gateway_ip: str  # 必填
    local_subnet: str | None = None
    default_node: str | None = None


class CertParseResult(BaseModel):
    """解析憑證 PEM 的結果"""

    valid: bool
    fingerprint: str | None = None  # SHA-256 指紋（冒號分隔大寫十六進位）
    subject: str | None = None
    issuer: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    error: str | None = None


class ProxmoxConnectionTestResult(BaseModel):
    """連線測試結果"""

    success: bool
    message: str


class ProxmoxNodePublic(BaseModel):
    """回傳給前端的節點資訊"""

    id: int | None = None
    name: str
    host: str
    port: int
    is_primary: bool
    is_online: bool
    last_checked: datetime | None = None


class ClusterPreviewResult(BaseModel):
    """偵測叢集節點的預覽結果（不儲存）"""

    success: bool
    is_cluster: bool          # True 代表有多個節點
    nodes: list[ProxmoxNodePublic]
    error: str | None = None


__all__ = [
    "ProxmoxConfigPublic",
    "ProxmoxConfigUpdate",
    "ProxmoxConnectionTestResult",
    "CertParseResult",
    "ProxmoxNodePublic",
    "ClusterPreviewResult",
]
