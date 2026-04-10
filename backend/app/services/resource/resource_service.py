import logging
import time
import uuid
from datetime import UTC, datetime

from sqlmodel import Session

from app.exceptions import BadRequestError, ProxmoxError
from app.repositories import vm_request as vm_request_repo
from app.schemas import ResourcePublic
from app.repositories import resource as resource_repo
from app.repositories import audit_log as audit_log_repo
from app.services.network import firewall_service
from app.services.proxmox import proxmox_service
from app.services.user import audit_service

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _enforce_start_window(*, session: Session, vmid: int) -> None:
    request = vm_request_repo.get_latest_approved_vm_request_by_vmid(
        session=session,
        vmid=vmid,
    )
    if not request or not request.start_at or not request.end_at:
        return

    now = _utc_now()
    start_at = request.start_at
    end_at = request.end_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=UTC)
    if end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=UTC)

    if now < start_at:
        raise BadRequestError("This resource can only be started when its approved time window begins.")
    if now >= end_at:
        raise BadRequestError("This resource can no longer be started because its approved time window has ended.")


def _from_punycode_hostname(hostname: str) -> str:
    """將 Punycode hostname 解碼回 Unicode 顯示給使用者。"""
    result_labels = []
    for label in hostname.split("."):
        if label.lower().startswith("xn--"):
            try:
                decoded = label[4:].encode("ascii").decode("punycode")
                result_labels.append(decoded)
            except Exception:
                result_labels.append(label)
        else:
            result_labels.append(label)
    return ".".join(result_labels)


def _build_resource_public(
    resource: dict, db_resource, node: str, vm_type: str,
    session: Session | None = None,
) -> ResourcePublic:
    vmid = resource.get("vmid")
    ip_address = proxmox_service.get_ip_address(node, vmid, vm_type)
    if ip_address:
        if session is not None:
            try:
                resource_repo.update_ip_address(
                    session=session, vmid=vmid, ip_address=ip_address
                )
            except Exception:
                logger.warning(
                    "Failed to update cached IP address for vmid=%s ip_address=%s",
                    vmid,
                    ip_address,
                    exc_info=True,
                )
    else:
        # VM 離線時用 DB 快取
        if db_resource and db_resource.ip_address:
            ip_address = db_resource.ip_address
    return ResourcePublic(
        vmid=resource.get("vmid"),
        name=_from_punycode_hostname(resource.get("name", "")),
        status=resource.get("status", ""),
        node=node,
        type=vm_type,
        environment_type=db_resource.environment_type if db_resource else None,
        os_info=db_resource.os_info if db_resource else None,
        expiry_date=db_resource.expiry_date if db_resource else None,
        ip_address=ip_address,
        cpu=resource.get("cpu"),
        maxcpu=resource.get("maxcpu"),
        mem=resource.get("mem"),
        maxmem=resource.get("maxmem"),
        uptime=resource.get("uptime"),
    )


def list_all(
    *, session: Session, node: str | None = None
) -> list[ResourcePublic]:
    try:
        resources = proxmox_service.list_all_resources()
        result = []
        for r in resources:
            if (node and r.get("node") != node) or r.get("template") == 1:
                continue
            vmid = r.get("vmid")
            vm_type = r.get("type")
            vm_node = r.get("node")
            db_resource = resource_repo.get_resource_by_vmid(
                session=session, vmid=vmid
            )
            result.append(
                _build_resource_public(r, db_resource, vm_node, vm_type, session)
            )
        return result
    except Exception as e:
        logger.error(f"Failed to get resources: {e}")
        raise ProxmoxError(f"Failed to get resources: {e}")


def list_by_user(
    *, session: Session, user_id: uuid.UUID
) -> list[ResourcePublic]:
    try:
        user_resources = resource_repo.get_resources_by_user(
            session=session, user_id=user_id
        )
        if not user_resources:
            return []

        owned_vmids = {r.vmid: r for r in user_resources}
        resources = proxmox_service.list_all_resources()
        result = []
        for r in resources:
            if r.get("template") == 1:
                continue
            vmid = r.get("vmid")
            if vmid not in owned_vmids:
                continue
            vm_type = r.get("type")
            vm_node = r.get("node")
            result.append(
                _build_resource_public(
                    r, owned_vmids[vmid], vm_node, vm_type, session
                )
            )
        return result
    except Exception as e:
        logger.error(f"Failed to get user resources: {e}")
        raise ProxmoxError(f"Failed to get user resources: {e}")


def get_config(*, vmid: int, resource_info: dict) -> dict:
    try:
        node = resource_info["node"]
        resource_type = resource_info["type"]
        return proxmox_service.get_config(node, vmid, resource_type)
    except Exception as e:
        logger.error(f"Failed to get config for {vmid}: {e}")
        raise ProxmoxError(f"Failed to get config for resource {vmid}: {e}")


def control(
    *,
    session: Session,
    vmid: int,
    action: str,
    resource_info: dict,
    user_id: uuid.UUID,
) -> dict:
    """Control a resource: start, stop, reboot, shutdown, reset."""
    valid_actions = {"start", "stop", "reboot", "shutdown", "reset"}
    if action not in valid_actions:
        raise BadRequestError(f"Invalid action: {action}")

    try:
        node = resource_info["node"]
        resource_type = resource_info["type"]

        if action == "start":
            _enforce_start_window(session=session, vmid=vmid)

        proxmox_service.control(node, vmid, resource_type, action)

        # 啟動時確保防火牆仍為啟用狀態
        if action == "start":
            firewall_service.ensure_firewall_enabled(node, vmid, resource_type)

        action_map = {
            "start": "resource_start",
            "stop": "resource_stop",
            "reboot": "resource_reboot",
            "shutdown": "resource_shutdown",
            "reset": "resource_reset",
        }
        audit_service.log_action(
            session=session,
            user_id=user_id,
            vmid=vmid,
            action=action_map[action],
            details=f"{action.capitalize()} {resource_type} {resource_info.get('name', vmid)}",
        )

        logger.info(f"Resource {vmid} {action}")
        return {"message": f"Resource {vmid} {action}"}
    except BadRequestError:
        raise
    except Exception as e:
        logger.error(f"Failed to {action} resource {vmid}: {e}")
        raise ProxmoxError(f"Failed to {action} resource {vmid}: {e}")


def delete(
    *,
    session: Session,
    vmid: int,
    resource_info: dict,
    user_id: uuid.UUID,
    purge: bool = True,
    force: bool = False,
) -> dict:
    try:
        node = resource_info["node"]
        resource_type = resource_info["type"]

        # Force stop if running
        current_status = resource_info.get("status", "")
        if current_status == "running":
            if not force:
                raise BadRequestError(
                    f"Resource {vmid} is running. Use force=true to stop and delete."
                )
            proxmox_service.control(node, vmid, resource_type, "stop")

            # Wait for stop
            for _ in range(30):
                time.sleep(1)
                try:
                    status = proxmox_service.get_status(node, vmid, resource_type)
                    if status.get("status") == "stopped":
                        break
                except Exception:
                    break

        # Delete the resource
        delete_params = {}
        if purge:
            delete_params["purge"] = 1
            if resource_type == "qemu":
                delete_params["destroy-unreferenced-disks"] = 1

        proxmox_service.delete_resource(node, vmid, resource_type, **delete_params)

        # Remove from database (resource record + all associated audit logs)
        resource_repo.delete_resource(session=session, vmid=vmid)
        audit_log_repo.delete_audit_logs_by_vmid(session=session, vmid=vmid)

        audit_service.log_action(
            session=session,
            user_id=user_id,
            vmid=vmid,
            action="resource_delete",
            details=(
                f"Deleted {resource_type} {resource_info.get('name', vmid)} "
                f"(purge={purge}, force={force})"
            ),
        )

        logger.info(f"Resource {vmid} deleted")
        return {"message": f"Resource {vmid} deleted successfully"}
    except (BadRequestError, ProxmoxError):
        raise
    except Exception as e:
        logger.error(f"Failed to delete resource {vmid}: {e}")
        raise ProxmoxError(f"Failed to delete resource {vmid}: {e}")


def get_current_stats(*, vmid: int, resource_info: dict) -> dict:
    try:
        node = resource_info["node"]
        resource_type = resource_info["type"]
        s = proxmox_service.get_status(node, vmid, resource_type)
        return {
            "cpu": s.get("cpu"),
            "maxcpu": s.get("cpus") or s.get("maxcpu"),
            "mem": s.get("mem"),
            "maxmem": s.get("maxmem"),
            "disk": s.get("disk"),
            "maxdisk": s.get("maxdisk"),
            "netin": s.get("netin"),
            "netout": s.get("netout"),
            "uptime": s.get("uptime"),
            "status": s.get("status", "unknown"),
        }
    except Exception as e:
        logger.error(f"Failed to get current stats for {vmid}: {e}")
        raise ProxmoxError(f"Failed to get stats for resource {vmid}: {e}")


def get_rrd_stats(
    *, vmid: int, resource_info: dict, timeframe: str
) -> list[dict]:
    valid_timeframes = ["hour", "day", "week", "month", "year"]
    if timeframe not in valid_timeframes:
        raise BadRequestError(
            f"Invalid timeframe. Must be one of: {valid_timeframes}"
        )
    try:
        node = resource_info["node"]
        resource_type = resource_info["type"]
        return proxmox_service.get_rrd_data(node, vmid, resource_type, timeframe)
    except BadRequestError:
        raise
    except Exception as e:
        logger.error(f"Failed to get RRD stats for {vmid}: {e}")
        raise ProxmoxError(f"Failed to get RRD stats for resource {vmid}: {e}")


def direct_update_spec(
    *,
    session: Session,
    vmid: int,
    resource_info: dict,
    user_id: uuid.UUID,
    cores: int | None = None,
    memory: int | None = None,
    disk_size: str | None = None,
) -> dict:
    """Admin direct spec update (no approval needed)."""
    try:
        node = resource_info["node"]
        resource_type = resource_info["type"]

        changes = []
        config_params = {}

        if cores is not None:
            config_params["cores"] = cores
            changes.append(f"CPU: {cores} cores")
        if memory is not None:
            config_params["memory"] = memory
            changes.append(f"Memory: {memory}MB")

        if not config_params and not disk_size:
            raise BadRequestError(
                "At least one specification must be provided"
            )

        if config_params:
            proxmox_service.update_config(
                node, vmid, resource_type, **config_params
            )

        if disk_size:
            disk_name = "scsi0" if resource_type == "qemu" else "rootfs"
            proxmox_service.resize_disk(
                node, vmid, resource_type, disk_name, disk_size
            )
            changes.append(f"Disk: {disk_size}")

        audit_service.log_action(
            session=session,
            user_id=user_id,
            vmid=vmid,
            action="spec_direct_update",
            details=f"Direct spec update: {', '.join(changes)}",
        )

        return {"message": f"Spec updated: {', '.join(changes)}"}
    except (BadRequestError, ProxmoxError):
        raise
    except Exception as e:
        logger.error(f"Failed to update spec for {vmid}: {e}")
        raise ProxmoxError(f"Failed to update spec for resource {vmid}: {e}")
