"""Teacher Judge target IP resolution helpers."""

from __future__ import annotations

import logging
from datetime import timezone
from ipaddress import IPv4Interface
from typing import Any, cast

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.exceptions import NotFoundError, ProxmoxError
from app.infrastructure.proxmox import operations as proxmox_ops
from app.infrastructure.proxmox.client import get_connection_id_for_node
from app.models import IpAllocation, Resource
from app.repositories import resource as resource_repo

logger = logging.getLogger(__name__)


def resource_identity(resource: Resource) -> tuple[str, int | None]:
    """Distinguish a recycled VMID from the resource selected for this run."""
    created = resource.created_at
    return (
        created.replace(tzinfo=created.tzinfo or timezone.utc)
        .astimezone(timezone.utc)
        .isoformat(),
        resource.connection_id,
    )


def _static_ipv4(value: str) -> str:
    try:
        ip = str(IPv4Interface(value).ip)
    except ValueError:
        return ""
    return ip if proxmox_ops._is_usable_ipv4(ip) else ""


def _configured_ip(config: dict[str, Any], resource_type: str) -> str:
    # Provisioning configures the managed NIC at net0 / ipconfig0.
    value = str(config.get("net0" if resource_type == "lxc" else "ipconfig0") or "")
    fields = dict(part.split("=", 1) for part in value.split(",") if "=" in part)
    return _static_ipv4(fields.get("ip", ""))


def refresh_target_ip_address(
    *,
    bind: Engine,
    vmid: int,
    user_id: str,
    identity: tuple[str, int | None],
    failed_ip: str,
) -> dict[str, Any]:
    """One uncached reconciliation after TCP failure; no transaction during PVE I/O."""
    result: dict[str, Any] = {"status": "unavailable", "ip_address": "", "source": None}

    def matches(resource: Resource | None) -> bool:
        return bool(
            resource
            and str(resource.user_id) == user_id
            and resource_identity(resource) == identity
        )

    with Session(bind) as session:
        if not matches(session.get(Resource, vmid)):
            return {**result, "status": "target_changed"}
        allocations = list(
            session.exec(
                select(IpAllocation.ip_address).where(IpAllocation.vmid == vmid)
            ).all()
        )
        if len(allocations) > 1:
            return {**result, "status": "allocation_conflict"}
        allocated = allocations[0] if allocations else ""
        if allocated and _static_ipv4(allocated) != allocated:
            return {**result, "status": "invalid_allocation"}
        network = resource_repo.get_resource_network_by_vmid(session=session, vmid=vmid)
        version = (network.ip_address, network.updated_at) if network else None
    result["allocated_ip"] = allocated or None

    configured = ""
    live: dict[str, Any] = {}
    try:
        proxmox_ops.invalidate_cluster_resources_cache()
        live = proxmox_ops.find_resource(vmid, strict=True)
    except proxmox_ops.ProxmoxConnectionUnavailableError:
        result["pve_status"] = "unavailable"
    except (NotFoundError, ProxmoxError):
        # A missing/ambiguous resource is not a reason to try another machine.
        return {**result, "status": "resource_unresolved"}
    if live:
        node, resource_type = str(live.get("node") or ""), str(live.get("type") or "")
        if (
            not node
            or resource_type not in {"lxc", "qemu"}
            or live.get("status") != "running"
        ):
            return {**result, "status": "resource_not_running"}
        if (
            identity[1] is not None
            and get_connection_id_for_node(node) != identity[1]
        ):
            return {**result, "status": "target_changed"}
        result.update(proxmox_node=node, resource_type=resource_type)
        try:
            configured = _configured_ip(
                proxmox_ops.get_config(
                    node,
                    vmid,
                    cast(proxmox_ops.ResourceType, resource_type),
                    current=True,
                ),
                resource_type,
            )
            result["pve_status"] = "checked"
        except Exception:
            result["pve_status"] = "config_unavailable"
    result["configured_ip"] = configured or None
    if allocated and configured and allocated != configured:
        return {**result, "status": "configuration_conflict"}
    candidate = allocated or configured
    source = "ip_allocation" if allocated else "proxmox_config"
    if not candidate and live and result.get("pve_status") == "checked":
        addresses = proxmox_ops.get_ip_addresses(
            result["proxmox_node"],
            vmid,
            cast(proxmox_ops.ResourceType, result["resource_type"]),
        )
        if len(addresses) != 1:
            return {
                **result,
                "status": "ambiguous_guest_ip" if addresses else "missing_ip",
            }
        candidate, source = addresses[0], "proxmox_guest"
    if not candidate:
        return result

    # Re-read identity, allocation and cache after PVE I/O. All cache writers
    # lock Resource first, so a later observation cannot blindly undo this write.
    with Session(bind) as session:
        resource = session.exec(
            select(Resource).where(Resource.vmid == vmid).with_for_update()
        ).first()
        if not matches(resource):
            return {**result, "status": "target_changed"}
        current_allocations = list(
            session.exec(
                select(IpAllocation.ip_address)
                .where(IpAllocation.vmid == vmid)
                .with_for_update()
            ).all()
        )
        network = resource_repo.get_resource_network_by_vmid(session=session, vmid=vmid)
        current_version = (network.ip_address, network.updated_at) if network else None
        if current_allocations != allocations or current_version != version:
            return {**result, "status": "state_changed"}
        holder = session.exec(
            select(IpAllocation).where(IpAllocation.ip_address == candidate)
        ).first()
        if holder is not None and holder.vmid != vmid:
            return {**result, "status": "ip_owned_elsewhere"}
        result.update(
            ip_address=candidate,
            source=source,
            status="unchanged" if candidate == failed_ip else "changed",
        )
        try:
            resource_repo.update_ip_address(
                session=session, vmid=vmid, ip_address=candidate, source=source
            )
            session.commit()
            result["cache_write"] = "saved"
        except Exception:
            session.rollback()
            result["cache_write"] = "failed"
            logger.warning(
                "Teacher Judge IP cache write failed vmid=%s", vmid, exc_info=True
            )
    return result


def resolve_target_ip_address(
    *,
    session: Session,
    vmid: int,
    live_resource: dict[str, Any] | None = None,
) -> str:
    """Resolve target IP from cache, Proxmox live state, then IP allocation."""
    cached_ip = (
        resource_repo.get_cached_ip_address(session=session, vmid=vmid) or ""
    ).strip()
    if cached_ip:
        return cached_ip

    node = str((live_resource or {}).get("node") or "")
    resource_type = str((live_resource or {}).get("type") or "")
    if not node or resource_type not in {"qemu", "lxc"}:
        try:
            found = proxmox_ops.find_resource(vmid)
        except Exception as exc:
            logger.warning("VMID %s live resource lookup failed: %s", vmid, exc)
            found = {}
        node = str(found.get("node") or "")
        resource_type = str(found.get("type") or "")

    live_ip = ""
    if node and resource_type in {"qemu", "lxc"}:
        try:
            live_ip = (
                proxmox_ops.get_ip_address(
                    node,
                    vmid,
                    cast(proxmox_ops.ResourceType, resource_type),
                )
                or ""
            ).strip()
        except Exception as exc:
            logger.warning("VMID %s live IP lookup failed: %s", vmid, exc)

    # Reuse the repository fallback when live discovery is unavailable.
    # Only observed live IPs are written back to the cache.
    return (
        resource_repo.sync_ip_cache(session=session, vmid=vmid, live_ip=live_ip or None)
        or ""
    ).strip()
