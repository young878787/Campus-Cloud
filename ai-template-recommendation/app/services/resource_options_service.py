from __future__ import annotations

import asyncio
from copy import deepcopy
from time import perf_counter
from typing import Any

from app.services.proxmox_templates_service import fetch_all_templates

RESOURCE_OPTIONS_CACHE_TTL_SECONDS = 30.0
_resource_options_cache: dict[str, list[dict[str, Any]]] | None = None
_resource_options_cache_expires_at = 0.0
_resource_options_cache_lock: asyncio.Lock | None = None


def _empty_resource_options() -> dict[str, list[dict[str, Any]]]:
    return {"lxc_os_images": [], "vm_operating_systems": []}


def _get_resource_options_cache_lock() -> asyncio.Lock:
    global _resource_options_cache_lock
    if _resource_options_cache_lock is None:
        _resource_options_cache_lock = asyncio.Lock()
    return _resource_options_cache_lock


def _cache_is_fresh(now: float) -> bool:
    return _resource_options_cache is not None and now < _resource_options_cache_expires_at


def _build_resource_options(
    lxc_raw: list[dict[str, Any]],
    vm_raw: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
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
    global _resource_options_cache, _resource_options_cache_expires_at
    del auth_header
    now = perf_counter()
    if _cache_is_fresh(now):
        return deepcopy(_resource_options_cache)

    cache_lock = _get_resource_options_cache_lock()
    async with cache_lock:
        now = perf_counter()
        if _cache_is_fresh(now):
            return deepcopy(_resource_options_cache)

        try:
            lxc_raw, vm_raw = await fetch_all_templates()
            resource_options = _build_resource_options(lxc_raw, vm_raw)
        except Exception:
            resource_options = _empty_resource_options()

        _resource_options_cache = resource_options
        _resource_options_cache_expires_at = perf_counter() + RESOURCE_OPTIONS_CACHE_TTL_SECONDS
        return deepcopy(resource_options)
