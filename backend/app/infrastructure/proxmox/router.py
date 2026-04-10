from __future__ import annotations

import logging

from proxmoxer import ProxmoxAPI

from app.infrastructure.proxmox.settings import ProxmoxSettings
from app.infrastructure.proxmox.tls import _tcp_ping, _verify_server_with_ca

logger = logging.getLogger(__name__)


def get_nodes_for_ha() -> list:
    """Fetch candidate HA nodes from DB ordered by configured priority."""
    try:
        from sqlmodel import Session

        from app.core.db import engine
        from app.repositories.proxmox_node import get_all_nodes

        with Session(engine) as session:
            return get_all_nodes(session)
    except Exception as exc:
        logger.warning("Unable to read Proxmox HA nodes from database: %s", exc)
        return []


def update_node_online(node_id: int, is_online: bool) -> None:
    """Best-effort status update; failures must not block client routing."""
    try:
        from sqlmodel import Session

        from app.core.db import engine
        from app.repositories.proxmox_node import update_node_status

        with Session(engine) as session:
            update_node_status(session, node_id, is_online)
    except Exception:
        return


def try_connect(host: str, cfg: ProxmoxSettings) -> ProxmoxAPI:
    """Create and validate a proxmoxer client for the selected host."""
    if cfg.ca_cert:
        _verify_server_with_ca(host, cfg.ca_cert)
        verify_ssl: bool = False
    else:
        verify_ssl = cfg.verify_ssl

    client = ProxmoxAPI(
        host,
        user=cfg.user,
        password=cfg.password,
        verify_ssl=verify_ssl,
        timeout=cfg.api_timeout,
    )
    client.version.get()
    return client


def fetch_cluster_nodes(
    host: str,
    user: str,
    password: str,
    verify_ssl: bool | str,
    timeout: int,
) -> list[dict]:
    """Return cluster node metadata from /cluster/status with single-node fallback."""
    client = ProxmoxAPI(
        host,
        user=user,
        password=password,
        verify_ssl=verify_ssl,
        timeout=timeout,
    )

    try:
        cluster_status = client.cluster.status.get()
    except Exception:
        return [{"name": host, "host": host, "port": 8006, "is_primary": True}]

    nodes = []
    for item in cluster_status:
        if item.get("type") != "node":
            continue
        node_host = item.get("ip") or item.get("name")
        nodes.append(
            {
                "name": item["name"],
                "host": node_host,
                "port": 8006,
                "is_primary": item.get("local") == 1,
            }
        )

    if not nodes:
        return [{"name": host, "host": host, "port": 8006, "is_primary": True}]

    if not any(node["is_primary"] for node in nodes):
        nodes[0]["is_primary"] = True

    return nodes
