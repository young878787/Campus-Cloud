from __future__ import annotations

import threading
import time
from typing import Any

from proxmoxer import ProxmoxAPI

from app.core.config import settings
from app.schemas import NodeSnapshot, ResourceSnapshot


_proxmox_client: ProxmoxAPI | None = None
_proxmox_created_at: float = 0.0
_proxmox_lock = threading.Lock()
_proxmox_ticket_ttl = 7000


def fetch_nodes() -> list[NodeSnapshot]:
    proxmox = _get_proxmox_api()
    nodes: list[NodeSnapshot] = []
    gpu_map = settings.parsed_backend_node_gpu_map
    for item in proxmox.nodes.get():
        node_name = str(item.get("node") or "unknown")
        nodes.append(
            NodeSnapshot(
                node=node_name,
                status=str(item.get("status") or "unknown"),
                cpu_ratio=float(item.get("cpu") or 0.0),
                maxcpu=int(item.get("maxcpu") or 0),
                mem_bytes=int(item.get("mem") or 0),
                maxmem_bytes=int(item.get("maxmem") or 0),
                disk_bytes=int(item.get("disk") or 0),
                maxdisk_bytes=int(item.get("maxdisk") or 0),
                uptime=_optional_int(item.get("uptime")),
                gpu_count=gpu_map.get(node_name, 0),
            )
        )
    return nodes


def fetch_resources() -> list[ResourceSnapshot]:
    proxmox = _get_proxmox_api()
    resources: list[ResourceSnapshot] = []
    for item in proxmox.cluster.resources.get(type="vm"):
        if item.get("template") == 1:
            continue
        resources.append(
            ResourceSnapshot(
                vmid=int(item.get("vmid") or 0),
                name=str(item.get("name") or ""),
                resource_type=str(item.get("type") or "unknown"),
                node=str(item.get("node") or "unknown"),
                status=str(item.get("status") or "unknown"),
                cpu_ratio=float(item.get("cpu") or 0.0),
                maxcpu=int(item.get("maxcpu") or 0),
                mem_bytes=int(item.get("mem") or 0),
                maxmem_bytes=int(item.get("maxmem") or 0),
                disk_bytes=int(item.get("disk") or 0),
                maxdisk_bytes=int(item.get("maxdisk") or 0),
                uptime=_optional_int(item.get("uptime")),
            )
        )
    return resources


def _get_proxmox_api() -> ProxmoxAPI:
    global _proxmox_client, _proxmox_created_at

    if not settings.proxmox_user or not settings.proxmox_password:
        raise RuntimeError("PROXMOX_USER and PROXMOX_PASSWORD are required for direct Proxmox mode.")

    now = time.monotonic()
    if _proxmox_client is not None and (now - _proxmox_created_at) < _proxmox_ticket_ttl:
        return _proxmox_client

    with _proxmox_lock:
        if _proxmox_client is not None and (now - _proxmox_created_at) < _proxmox_ticket_ttl:
            return _proxmox_client

        _proxmox_client = ProxmoxAPI(
            settings.proxmox_host,
            user=settings.proxmox_user,
            password=settings.proxmox_password,
            verify_ssl=settings.proxmox_verify_ssl,
            timeout=settings.proxmox_api_timeout,
        )
        _proxmox_created_at = now
        return _proxmox_client


def _optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
