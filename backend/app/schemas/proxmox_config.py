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
    placement_strategy: str = "dominant_share_min"
    cpu_overcommit_ratio: float = 2.0
    disk_overcommit_ratio: float = 1.0
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
    gateway_ip: str | None = None
    local_subnet: str | None = None
    default_node: str | None = None
    placement_strategy: str = "dominant_share_min"
    cpu_overcommit_ratio: float = Field(default=2.0, ge=1.0, le=8.0)
    disk_overcommit_ratio: float = Field(default=1.0, ge=1.0, le=5.0)


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
    priority: int = 5


class ProxmoxNodeUpdate(BaseModel):
    """更新單一節點設定的請求 schema"""

    host: str
    port: int = Field(default=8006, ge=1, le=65535)
    priority: int = Field(default=5, ge=1, le=10)


class ClusterPreviewResult(BaseModel):
    """偵測叢集節點的預覽結果（不儲存）"""

    success: bool
    is_cluster: bool          # True 代表有多個節點
    nodes: list[ProxmoxNodePublic]
    error: str | None = None


class ProxmoxStoragePublic(BaseModel):
    """回傳給前端的 Storage 資訊"""

    id: int
    node_name: str
    storage: str
    storage_type: str | None = None
    total_gb: float
    used_gb: float
    avail_gb: float
    can_vm: bool
    can_lxc: bool
    can_iso: bool
    can_backup: bool
    is_shared: bool
    active: bool
    enabled: bool
    speed_tier: str   # "nvme"|"ssd"|"hdd"|"unknown"
    user_priority: int


class ProxmoxStorageUpdate(BaseModel):
    """更新 Storage 使用者設定的請求 schema"""

    enabled: bool
    speed_tier: str = Field(pattern=r"^(nvme|ssd|hdd|unknown)$")
    user_priority: int = Field(ge=1, le=10)


class SyncNowResult(BaseModel):
    """同步節點與 Storage 結果"""

    success: bool
    nodes: list[ProxmoxNodePublic]
    storage_count: int
    error: str | None = None


class NodeStatsPublic(BaseModel):
    """單一節點的即時資源使用狀態"""

    name: str
    status: str
    cpu_usage_pct: float   # 0–100
    cpu_cores: int
    mem_used_gb: float
    mem_total_gb: float
    disk_used_gb: float
    disk_total_gb: float
    vm_count: int = 0


class ClusterStatsPublic(BaseModel):
    """整個叢集的資源加總與各節點狀態"""

    nodes: list[NodeStatsPublic]
    total_cpu_cores: int
    used_cpu_cores: float   # weighted sum from cpu_ratio * maxcpu
    total_mem_gb: float
    used_mem_gb: float
    total_disk_gb: float
    used_disk_gb: float
    online_count: int
    offline_count: int
    total_vm_count: int


__all__ = [
    "ProxmoxConfigPublic",
    "ProxmoxConfigUpdate",
    "ProxmoxConnectionTestResult",
    "CertParseResult",
    "ProxmoxNodePublic",
    "ClusterPreviewResult",
    "ProxmoxNodeUpdate",
    "ProxmoxStoragePublic",
    "ProxmoxStorageUpdate",
    "SyncNowResult",
    "NodeStatsPublic",
    "ClusterStatsPublic",
]
