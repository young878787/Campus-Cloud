"""Centralized Proxmox VE API operations.

Provides a single place for common PVE interactions (resource lookup, config,
control, resize, specs, session ticket, etc.) so that callers no longer
duplicate the same cluster.resources iteration or qemu/lxc dispatch logic.
"""

import logging
from typing import Literal

import httpx

from app.core.config import settings
from app.core.proxmox import basic_blocking_task_status, get_proxmox_api
from app.exceptions import NotFoundError, ProxmoxError

logger = logging.getLogger(__name__)

DEFAULT_NODE = "pve"

ResourceType = Literal["qemu", "lxc"]


# ---------------------------------------------------------------------------
# Resource lookup
# ---------------------------------------------------------------------------

def find_resource(vmid: int) -> dict:
    """Find any resource (qemu or lxc) by VMID in the cluster."""
    proxmox = get_proxmox_api()
    for r in proxmox.cluster.resources.get(type="vm"):
        if r["vmid"] == vmid:
            return r
    raise NotFoundError(f"Resource {vmid} not found")


def find_lxc(vmid: int) -> dict:
    """Find an LXC container by VMID (raises if not found or not lxc)."""
    proxmox = get_proxmox_api()
    for r in proxmox.cluster.resources.get(type="vm"):
        if r["vmid"] == vmid and r["type"] == "lxc":
            return r
    raise NotFoundError(f"LXC container {vmid} not found")


def list_all_resources() -> list[dict]:
    """Return all cluster resources of type vm."""
    proxmox = get_proxmox_api()
    return proxmox.cluster.resources.get(type="vm")


def list_nodes() -> list[dict]:
    """Return all cluster nodes."""
    proxmox = get_proxmox_api()
    return proxmox.nodes.get()


# ---------------------------------------------------------------------------
# Node helper — dispatches qemu / lxc transparently
# ---------------------------------------------------------------------------

def _resource_api(node: str, vmid: int, resource_type: ResourceType):
    """Return the proxmoxer node resource handle (qemu or lxc)."""
    proxmox = get_proxmox_api()
    if resource_type == "qemu":
        return proxmox.nodes(node).qemu(vmid)
    return proxmox.nodes(node).lxc(vmid)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config(node: str, vmid: int, resource_type: ResourceType) -> dict:
    """GET /nodes/{node}/{type}/{vmid}/config"""
    return _resource_api(node, vmid, resource_type).config.get()


def update_config(
    node: str, vmid: int, resource_type: ResourceType, **params
) -> None:
    """PUT /nodes/{node}/{type}/{vmid}/config"""
    _resource_api(node, vmid, resource_type).config.put(**params)


# ---------------------------------------------------------------------------
# Control (start / stop / reboot / shutdown / reset)
# ---------------------------------------------------------------------------

def control(
    node: str, vmid: int, resource_type: ResourceType, action: str
) -> None:
    """Execute a power action on a resource."""
    getattr(_resource_api(node, vmid, resource_type).status, action).post()


def get_status(node: str, vmid: int, resource_type: ResourceType) -> dict:
    """GET /nodes/{node}/{type}/{vmid}/status/current"""
    return _resource_api(node, vmid, resource_type).status.current.get()


# ---------------------------------------------------------------------------
# Disk resize
# ---------------------------------------------------------------------------

def resize_disk(
    node: str,
    vmid: int,
    resource_type: ResourceType,
    disk: str,
    size: str,
) -> None:
    """PUT /nodes/{node}/{type}/{vmid}/resize"""
    _resource_api(node, vmid, resource_type).resize.put(disk=disk, size=size)


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def list_snapshots(node: str, vmid: int, resource_type: ResourceType) -> list:
    return _resource_api(node, vmid, resource_type).snapshot.get()


def create_snapshot(
    node: str, vmid: int, resource_type: ResourceType, **params
) -> str:
    task = _resource_api(node, vmid, resource_type).snapshot.post(**params)
    basic_blocking_task_status(node, task)
    return task


def delete_snapshot(
    node: str, vmid: int, resource_type: ResourceType, snapname: str
) -> str:
    task = _resource_api(node, vmid, resource_type).snapshot(snapname).delete()
    basic_blocking_task_status(node, task)
    return task


def rollback_snapshot(
    node: str, vmid: int, resource_type: ResourceType, snapname: str
) -> str:
    task = _resource_api(node, vmid, resource_type).snapshot(snapname).rollback.post()
    basic_blocking_task_status(node, task)
    return task


# ---------------------------------------------------------------------------
# RRD stats
# ---------------------------------------------------------------------------

def get_rrd_data(
    node: str, vmid: int, resource_type: ResourceType, timeframe: str
) -> list[dict]:
    return _resource_api(node, vmid, resource_type).rrddata.get(timeframe=timeframe)


# ---------------------------------------------------------------------------
# Delete resource
# ---------------------------------------------------------------------------

def delete_resource(
    node: str, vmid: int, resource_type: ResourceType, **params
) -> str:
    task = _resource_api(node, vmid, resource_type).delete(**params)
    basic_blocking_task_status(node, task)
    return task


# ---------------------------------------------------------------------------
# IP address
# ---------------------------------------------------------------------------

def get_ip_address(node: str, vmid: int, resource_type: ResourceType) -> str | None:
    proxmox = get_proxmox_api()
    try:
        if resource_type == "lxc":
            interfaces = proxmox.nodes(node).lxc(vmid).interfaces.get()
            for iface in interfaces:
                if iface.get("name") in ["eth0", "net0"]:
                    inet = iface.get("inet")
                    if inet:
                        return inet.split("/")[0]
        else:
            try:
                network_info = (
                    proxmox.nodes(node)
                    .qemu(vmid)("agent")("network-get-interfaces")
                    .get()
                )
                if network_info and "result" in network_info:
                    for iface in network_info["result"]:
                        if iface.get("name") in ["eth0", "ens18"]:
                            for ip in iface.get("ip-addresses", []):
                                if (
                                    ip.get("ip-address-type") == "ipv4"
                                    and not ip.get("ip-address", "").startswith("127.")
                                ):
                                    return ip.get("ip-address")
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Failed to get IP for VMID {vmid}: {e}")
    return None


# ---------------------------------------------------------------------------
# Current specs (parsed from config)
# ---------------------------------------------------------------------------

def get_current_specs(node: str, vmid: int, resource_type: ResourceType) -> dict:
    """Returns {"cpu": int|None, "memory": int|None, "disk": int|None}."""
    config = get_config(node, vmid, resource_type)

    current_cpu = config.get("cores") or config.get("cpus")
    current_memory = config.get("memory")
    current_disk = None

    if resource_type == "qemu":
        scsi0 = config.get("scsi0", "")
        if "size=" in scsi0:
            size_str = scsi0.split("size=")[1].split(",")[0].split(")")[0]
            if size_str.endswith("G"):
                current_disk = int(size_str[:-1])
    else:
        rootfs = config.get("rootfs", "")
        if "size=" in rootfs:
            size_str = rootfs.split("size=")[1].split(",")[0]
            if size_str.endswith("G"):
                current_disk = int(size_str[:-1])

    return {"cpu": current_cpu, "memory": current_memory, "disk": current_disk}


# ---------------------------------------------------------------------------
# LXC creation
# ---------------------------------------------------------------------------

def create_lxc(node: str, **config) -> str:
    """Create an LXC container and wait for the task to finish. Returns UPID."""
    proxmox = get_proxmox_api()
    task = proxmox.nodes(node).lxc.create(**config)
    basic_blocking_task_status(node, task)
    return task


# ---------------------------------------------------------------------------
# VM clone + configure
# ---------------------------------------------------------------------------

def clone_vm(node: str, template_id: int, **clone_config) -> str:
    """Clone a VM template and wait. Returns UPID."""
    proxmox = get_proxmox_api()
    task = proxmox.nodes(node).qemu(template_id).clone.post(**clone_config)
    basic_blocking_task_status(node, task)
    return task


def next_vmid() -> int:
    proxmox = get_proxmox_api()
    return proxmox.cluster.nextid.get()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def get_lxc_templates(node: str) -> list[dict]:
    proxmox = get_proxmox_api()
    return proxmox.nodes(node).storage(settings.PROXMOX_ISO_STORAGE).content.get()


def get_vm_templates() -> list[dict]:
    """Return all VM templates from the cluster."""
    return [vm for vm in list_all_resources() if vm.get("template") == 1]


# ---------------------------------------------------------------------------
# Session ticket (for WebSocket auth — password-based, not API token)
# ---------------------------------------------------------------------------

async def get_session_ticket() -> tuple[str, str]:
    """Authenticate via password and return (pve_auth_cookie, csrf_token).

    Proxmox WebSocket endpoints (termproxy, vncproxy) require a session
    ticket obtained via password auth; API tokens are not accepted.
    """
    async with httpx.AsyncClient(verify=settings.PROXMOX_VERIFY_SSL) as client:
        resp = await client.post(
            f"https://{settings.PROXMOX_HOST}:8006/api2/json/access/ticket",
            data={
                "username": settings.PROXMOX_USER,
                "password": settings.PROXMOX_PASSWORD,
            },
        )
        if resp.status_code != 200:
            raise ProxmoxError(
                f"Proxmox session authentication failed: HTTP {resp.status_code}"
            )
        data = resp.json()["data"]
        return data["ticket"], data.get("CSRFPreventionToken", "")


# ---------------------------------------------------------------------------
# Console tickets
# ---------------------------------------------------------------------------

def get_terminal_ticket(node: str, vmid: int) -> dict:
    """Get termproxy ticket for an LXC container (port + ticket)."""
    proxmox = get_proxmox_api()
    return proxmox.nodes(node).lxc(vmid).termproxy.post()


def get_vnc_ticket(node: str, vmid: int) -> dict:
    """Get VNC proxy ticket for a VM (port + ticket)."""
    proxmox = get_proxmox_api()
    return proxmox.nodes(node).qemu(vmid).vncproxy.post(websocket=1)
