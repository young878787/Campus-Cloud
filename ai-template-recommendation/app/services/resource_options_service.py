from __future__ import annotations

import asyncio
from typing import Any

from app.services.proxmox_templates_service import fetch_lxc_templates, fetch_vm_templates


def _derive_lxc_label(volid: str) -> str:
    filename = volid.split("/")[-1] if volid else ""
    return filename.replace(".tar.zst", "") or volid


def _derive_vm_os_family(name: str) -> str:
    normalized = name.lower()
    if "windows" in normalized:
        return "windows"
    for distro in ("ubuntu", "debian", "rocky", "alma", "centos", "fedora", "arch", "kali", "linux"):
        if distro in normalized:
            return distro
    return "other"


async def fetch_resource_options(auth_header: str | None = None) -> dict[str, list[dict[str, Any]]]:
    try:
        lxc_raw, vm_raw = await asyncio.gather(
            fetch_lxc_templates(),
            fetch_vm_templates(),
        )
    except Exception:
        return {"lxc_os_images": [], "vm_operating_systems": []}

    return {
        "lxc_os_images": [
            {
                "value": str(item.get("volid") or ""),
                "label": _derive_lxc_label(str(item.get("volid") or "")),
                "format": str(item.get("format") or ""),
                "size": int(item.get("size") or 0),
            }
            for item in lxc_raw
            if item.get("volid")
        ],
        "vm_operating_systems": [
            {
                "template_id": int(item.get("vmid") or 0),
                "label": str(item.get("name") or f"Template #{item.get('vmid') or ''}"),
                "template_name": str(item.get("name") or ""),
                "node": str(item.get("node") or ""),
                "os_family": _derive_vm_os_family(str(item.get("name") or "")),
            }
            for item in vm_raw
            if item.get("vmid")
        ],
    }
