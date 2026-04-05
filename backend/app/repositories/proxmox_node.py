"""Proxmox 節點資料庫操作"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.proxmox_node import ProxmoxNode


def get_all_nodes(session: Session) -> list[ProxmoxNode]:
    """取得所有節點，主節點優先，其餘按名稱排序。"""
    stmt = select(ProxmoxNode).order_by(
        ProxmoxNode.is_primary.desc(),  # type: ignore[attr-defined]
        ProxmoxNode.name,
    )
    return list(session.exec(stmt).all())


def upsert_nodes(
    session: Session,
    nodes: list[dict],
) -> list[ProxmoxNode]:
    """
    同步節點清單到資料庫。
    以 name 為 key：存在則更新 host/port/is_primary/is_online/last_checked，保留既有 priority；
    不存在則新建（priority 預設 5）。
    刪除本次同步中不再出現的舊節點。
    """
    existing_all = list(session.exec(select(ProxmoxNode)).all())
    existing_map: dict[str, ProxmoxNode] = {n.name: n for n in existing_all}

    incoming_names: set[str] = set()
    result: list[ProxmoxNode] = []

    for node_data in nodes:
        name = node_data["name"]
        incoming_names.add(name)

        if name in existing_map:
            node = existing_map[name]
            node.host = node_data["host"]
            node.port = node_data.get("port", 8006)
            node.is_primary = node_data.get("is_primary", False)
            node.is_online = True
            node.last_checked = datetime.now(timezone.utc)
            # 保留既有 priority，不覆寫
        else:
            node = ProxmoxNode(
                name=name,
                host=node_data["host"],
                port=node_data.get("port", 8006),
                is_primary=node_data.get("is_primary", False),
                is_online=True,
                last_checked=datetime.now(timezone.utc),
                priority=5,
            )
        session.add(node)
        result.append(node)

    # 刪除消失的節點
    for name, node in existing_map.items():
        if name not in incoming_names:
            session.delete(node)

    session.flush()
    session.commit()
    for node in result:
        session.refresh(node)
    return result


def update_node(
    session: Session,
    node_id: int,
    host: str,
    port: int,
    priority: int,
) -> ProxmoxNode | None:
    """更新單一節點的連線設定與優先級。"""
    node = session.get(ProxmoxNode, node_id)
    if node is None:
        return None
    node.host = host
    node.port = port
    node.priority = priority
    session.add(node)
    session.commit()
    session.refresh(node)
    return node


def update_node_status(session: Session, node_id: int, is_online: bool) -> None:
    """更新節點的連線狀態。"""
    node = session.get(ProxmoxNode, node_id)
    if node:
        node.is_online = is_online
        node.last_checked = datetime.now(timezone.utc)
        session.add(node)
        session.commit()


__all__ = [
    "get_all_nodes",
    "upsert_nodes",
    "update_node",
    "update_node_status",
]
