"""Proxmox Storage 資料庫操作"""

from sqlmodel import Session, select

from app.models.proxmox_storage import ProxmoxStorage


def get_all_storages(session: Session) -> list[ProxmoxStorage]:
    """取得所有已儲存的 Storage，按節點名稱 + storage 名稱排序。"""
    stmt = select(ProxmoxStorage).order_by(
        ProxmoxStorage.node_name,
        ProxmoxStorage.storage,
    )
    return list(session.exec(stmt).all())


def get_storages_by_node(session: Session, node_name: str) -> list[ProxmoxStorage]:
    """取得特定節點的所有 Storage。"""
    stmt = (
        select(ProxmoxStorage)
        .where(ProxmoxStorage.node_name == node_name)
        .order_by(ProxmoxStorage.storage)
    )
    return list(session.exec(stmt).all())


def upsert_storages(session: Session, storages: list[dict]) -> list[ProxmoxStorage]:
    """
    同步 Storage 清單到資料庫。
    以 (node_name, storage) 為 key：
    - 存在則只更新硬體資訊（total_gb/used_gb/avail_gb/type/flags/active）
    - 不存在則新建；保留既有的 enabled/speed_tier/user_priority 使用者設定。
    - 刪除本次同步中不再出現的舊 Storage。
    """
    existing_all = list(session.exec(select(ProxmoxStorage)).all())
    existing_map: dict[tuple[str, str], ProxmoxStorage] = {
        (s.node_name, s.storage): s for s in existing_all
    }

    incoming_keys: set[tuple[str, str]] = set()
    result: list[ProxmoxStorage] = []

    for data in storages:
        key = (data["node_name"], data["storage"])
        incoming_keys.add(key)

        if key in existing_map:
            s = existing_map[key]
            s.storage_type = data.get("storage_type")
            s.total_gb = data.get("total_gb", 0.0)
            s.used_gb = data.get("used_gb", 0.0)
            s.avail_gb = data.get("avail_gb", 0.0)
            s.can_vm = data.get("can_vm", False)
            s.can_lxc = data.get("can_lxc", False)
            s.can_iso = data.get("can_iso", False)
            s.can_backup = data.get("can_backup", False)
            s.is_shared = data.get("is_shared", False)
            s.active = data.get("active", True)
            session.add(s)
            result.append(s)
        else:
            s = ProxmoxStorage(
                node_name=data["node_name"],
                storage=data["storage"],
                storage_type=data.get("storage_type"),
                total_gb=data.get("total_gb", 0.0),
                used_gb=data.get("used_gb", 0.0),
                avail_gb=data.get("avail_gb", 0.0),
                can_vm=data.get("can_vm", False),
                can_lxc=data.get("can_lxc", False),
                can_iso=data.get("can_iso", False),
                can_backup=data.get("can_backup", False),
                is_shared=data.get("is_shared", False),
                active=data.get("active", True),
                enabled=data.get("can_vm", False) or data.get("can_lxc", False),
                speed_tier="unknown",
                user_priority=5,
            )
            session.add(s)
            result.append(s)

    for key, s in existing_map.items():
        if key not in incoming_keys:
            session.delete(s)

    session.flush()   # push deletes before commit, consistent with proxmox_node.py

    session.commit()
    for s in result:
        session.refresh(s)
    return result


def update_storage_settings(
    session: Session,
    storage_id: int,
    enabled: bool,
    speed_tier: str,
    user_priority: int,
) -> ProxmoxStorage | None:
    """更新使用者可設定的欄位（enabled, speed_tier, user_priority）。"""
    s = session.get(ProxmoxStorage, storage_id)
    if s is None:
        return None
    s.enabled = enabled
    s.speed_tier = speed_tier
    s.user_priority = user_priority
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


__all__ = [
    "get_all_storages",
    "get_storages_by_node",
    "upsert_storages",
    "update_storage_settings",
]
