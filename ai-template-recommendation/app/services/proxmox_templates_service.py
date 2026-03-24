from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings


def _proxmox_base_url() -> str:
    host = str(settings.proxmox_host or "").strip().rstrip("/")
    if not host:
        raise HTTPException(status_code=503, detail="PROXMOX_HOST is not configured")
    if host.startswith("http://") or host.startswith("https://"):
        return host
    scheme = "https"
    suffix = "" if host.endswith(":8006") else ":8006"
    return f"{scheme}://{host}{suffix}"


async def _get_auth_cookie() -> str:
    if not settings.proxmox_user or not settings.proxmox_password:
        raise HTTPException(status_code=503, detail="PROXMOX_USER / PROXMOX_PASSWORD are not configured")

    try:
        async with httpx.AsyncClient(verify=settings.proxmox_verify_ssl, timeout=settings.proxmox_api_timeout) as client:
            response = await client.post(
                f"{_proxmox_base_url()}/api2/json/access/ticket",
                data={
                    "username": settings.proxmox_user,
                    "password": settings.proxmox_password,
                },
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Proxmox auth endpoint: {exc}") from exc

    if not response.is_success:
        raise HTTPException(status_code=502, detail=f"Proxmox auth failed with status {response.status_code}")

    payload = response.json()
    ticket = str((((payload.get("data") or {}).get("ticket")) or "")).strip()
    if not ticket:
        raise HTTPException(status_code=502, detail="Proxmox auth returned no ticket")
    return ticket


async def _get_json(path: str) -> Any:
    ticket = await _get_auth_cookie()
    try:
        async with httpx.AsyncClient(
            verify=settings.proxmox_verify_ssl,
            timeout=settings.proxmox_api_timeout,
            cookies={"PVEAuthCookie": ticket},
        ) as client:
            response = await client.get(f"{_proxmox_base_url()}{path}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Proxmox {path}: {exc}") from exc

    if not response.is_success:
        raise HTTPException(status_code=502, detail=f"Proxmox returned {response.status_code} for {path}")

    return response.json()


async def fetch_lxc_templates() -> list[dict[str, Any]]:
    payload = await _get_json(
        f"/api2/json/nodes/{settings.proxmox_node}/storage/{settings.proxmox_iso_storage}/content"
    )
    raw_items = list((payload.get("data") or []))
    return [
        {
            "volid": str(item.get("volid") or ""),
            "format": str(item.get("format") or ""),
            "size": int(item.get("size") or 0),
        }
        for item in raw_items
        if item.get("content") == "vztmpl" and item.get("volid")
    ]


async def fetch_vm_templates() -> list[dict[str, Any]]:
    payload = await _get_json("/api2/json/cluster/resources?type=vm")
    raw_items = list((payload.get("data") or []))
    return [
        {
            "vmid": int(item.get("vmid") or 0),
            "name": str(item.get("name") or f"template-{item.get('vmid') or ''}"),
            "node": str(item.get("node") or ""),
        }
        for item in raw_items
        if item.get("template") == 1 and item.get("vmid")
    ]
