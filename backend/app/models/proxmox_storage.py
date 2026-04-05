"""Proxmox Storage 設定模型"""

from sqlmodel import Field, SQLModel


class ProxmoxStorage(SQLModel, table=True):
    """每個節點的 Storage pool 設定（含 simulator 用的速度分級與優先級）"""

    __tablename__ = "proxmox_storages"

    id: int | None = Field(default=None, primary_key=True)
    node_name: str = Field(max_length=255)       # 所屬節點名稱（如 "pve"）
    storage: str = Field(max_length=255)          # Storage 名稱（如 "local-lvm"）
    storage_type: str | None = Field(default=None, max_length=50)  # "dir", "lvm", "ceph" 等
    total_gb: float = Field(default=0.0)
    used_gb: float = Field(default=0.0)
    avail_gb: float = Field(default=0.0)
    can_vm: bool = Field(default=False)
    can_lxc: bool = Field(default=False)
    can_iso: bool = Field(default=False)
    can_backup: bool = Field(default=False)
    is_shared: bool = Field(default=False)
    active: bool = Field(default=True)
    # === 使用者可設定（simulator 用）===
    enabled: bool = Field(default=True)
    speed_tier: str = Field(default="unknown", max_length=20)  # "nvme"|"ssd"|"hdd"|"unknown"
    user_priority: int = Field(default=5, ge=1, le=10)


__all__ = ["ProxmoxStorage"]
