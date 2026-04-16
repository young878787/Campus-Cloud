from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel import Session, select

from app.exceptions import NotFoundError
from app.infrastructure.proxmox import get_proxmox_settings
from app.models import (
    VMMigrationJobStatus,
    VMMigrationStatus,
    VMRequest,
    VMRequestStatus,
)
from app.repositories import resource as resource_repo
from app.repositories import vm_migration_job as vm_migration_job_repo
from app.repositories import vm_request as vm_request_repo
from app.services.proxmox import proxmox_service
from app.services.scheduling import policy as scheduling_policy

logger = logging.getLogger(__name__)

_VM_DISK_PREFIXES = ("scsi", "sata", "ide", "virtio", "efidisk", "tpmstate")
_LXC_MOUNT_PREFIXES = ("rootfs", "mp")


def find_existing_resource_for_request(
    *,
    session: Session,
    request: VMRequest,
) -> dict | None:
    expected_type = scheduling_policy.resource_type_for_request(request)
    pool_name = get_proxmox_settings().pool_name
    _active_statuses = (
        VMRequestStatus.approved,
        VMRequestStatus.provisioning,
        VMRequestStatus.running,
    )
    claimed_vmids = {
        int(item.vmid)
        for item in session.exec(
            select(VMRequest).where(
                VMRequest.status.in_(_active_statuses),
                VMRequest.vmid.is_not(None),
                VMRequest.id != request.id,
            )
        ).all()
        if item.vmid is not None
    }
    # hostname is stored as punycode in DB since creation.
    expected_hostname = str(request.hostname or "")
    for resource in proxmox_service.list_all_resources():
        if str(resource.get("type") or "") != expected_type:
            continue
        resource_name = str(resource.get("name") or "")
        if resource_name != expected_hostname:
            continue
        vmid = int(resource.get("vmid"))
        if vmid in claimed_vmids:
            continue
        pool = str(resource.get("pool") or "")
        if pool and pool != pool_name:
            continue
        return resource
    return None


def mark_request_runtime_error(
    *,
    session: Session,
    request_id,
    message: str,
) -> None:
    request = vm_request_repo.get_vm_request_by_id(
        session=session,
        request_id=request_id,
        for_update=True,
    )
    if not request:
        return
    vm_request_repo.update_vm_request_provisioning(
        session=session,
        db_request=request,
        vmid=request.vmid,
        assigned_node=request.assigned_node,
        desired_node=request.desired_node,
        actual_node=request.actual_node,
        placement_strategy_used=request.placement_strategy_used,
        migration_status=VMMigrationStatus.failed,
        migration_error=message[:500],
        rebalance_epoch=request.rebalance_epoch,
        last_rebalanced_at=request.last_rebalanced_at,
        commit=False,
    )
    if any(
        keyword in message.lower()
        for keyword in ("no feasible", "capacity", "no node", "cannot fit")
    ):
        request.resource_warning = message[:500]
        session.add(request)
    session.commit()


def extract_storage_id(config_value: object) -> str | None:
    text = str(config_value or "").strip()
    if not text:
        return None
    if text.startswith("/"):
        return None
    if ":" not in text:
        return None
    return text.split(":", 1)[0].strip() or None


def storage_ids_available_on_node(*, node: str) -> set[str]:
    return {
        str(item.get("storage") or item.get("id") or "").strip()
        for item in proxmox_service.list_node_storages(node)
        if str(item.get("storage") or item.get("id") or "").strip()
    }


def detect_migration_pinned(
    *,
    node: str,
    vmid: int,
    resource_type: str,
) -> bool:
    try:
        config = proxmox_service.get_config(node, vmid, resource_type)
    except Exception:
        return False

    if resource_type == "qemu":
        if any(key.startswith(("hostpci", "usb")) for key in config):
            return True
        for key, value in config.items():
            if not key.startswith(_VM_DISK_PREFIXES):
                continue
            if str(value or "").strip().startswith("/"):
                return True
    else:
        for key, value in config.items():
            if not key.startswith(_LXC_MOUNT_PREFIXES):
                continue
            if str(value or "").strip().startswith("/"):
                return True
    return False


def migration_block_reason(
    *,
    source_node: str,
    target_node: str,
    vmid: int,
    resource_type: str,
) -> str | None:
    config = proxmox_service.get_config(source_node, vmid, resource_type)
    target_storages = storage_ids_available_on_node(node=target_node)

    if resource_type == "qemu":
        passthrough_keys = [
            key for key in config if key.startswith("hostpci") or key.startswith("usb")
        ]
        if passthrough_keys:
            return (
                "Migration blocked because this VM uses passthrough devices: "
                + ", ".join(sorted(passthrough_keys))
            )

        for key, value in config.items():
            if not key.startswith(_VM_DISK_PREFIXES):
                continue
            storage_id = extract_storage_id(value)
            if storage_id is None:
                if str(value or "").strip().startswith("/"):
                    return f"Migration blocked because disk '{key}' uses a direct path mount."
                continue
            if storage_id not in target_storages:
                return (
                    f"Migration blocked because target node '{target_node}' "
                    f"does not expose storage '{storage_id}' required by disk '{key}'."
                )
        return None

    for key, value in config.items():
        if not key.startswith(_LXC_MOUNT_PREFIXES):
            continue
        text = str(value or "").strip()
        if text.startswith("/"):
            return (
                f"Migration blocked because container mount '{key}' is a direct bind mount."
            )
        storage_id = extract_storage_id(value)
        if storage_id and storage_id not in target_storages:
            return (
                f"Migration blocked because target node '{target_node}' "
                f"does not expose storage '{storage_id}' required by mount '{key}'."
            )
    return None


def sync_request_migration_job(
    *,
    session: Session,
    request: VMRequest,
    source_node: str | None,
    now: datetime,
) -> None:
    desired_node = str(request.desired_node or request.assigned_node or "")
    actual_node = str(source_node or request.actual_node or request.assigned_node or "")
    if request.vmid is None:
        vm_migration_job_repo.cancel_pending_jobs_for_request(
            session=session,
            request_id=request.id,
            reason="Migration queue cleared because the request no longer has a VMID.",
            commit=False,
        )
        return
    if not desired_node:
        vm_migration_job_repo.cancel_pending_jobs_for_request(
            session=session,
            request_id=request.id,
            reason=(
                "Migration queue cleared because the request no longer has a "
                "desired target node."
            ),
            commit=False,
        )
        return
    if desired_node == actual_node:
        vm_migration_job_repo.cancel_pending_jobs_for_request(
            session=session,
            request_id=request.id,
            reason="Migration queue cleared because the request is already on the target node.",
            commit=False,
        )
        return

    latest_job = vm_migration_job_repo.get_latest_job_for_request(
        session=session,
        request_id=request.id,
    )
    if (
        latest_job is not None
        and latest_job.status in {VMMigrationJobStatus.failed, VMMigrationJobStatus.blocked}
        and int(latest_job.rebalance_epoch or 0) == int(request.rebalance_epoch or 0)
        and str(latest_job.target_node or "") == desired_node
    ):
        return
    if (
        latest_job is not None
        and latest_job.status in {VMMigrationJobStatus.pending, VMMigrationJobStatus.running}
        and int(latest_job.rebalance_epoch or 0) == int(request.rebalance_epoch or 0)
        and str(latest_job.target_node or "") == desired_node
        and str(latest_job.source_node or "") == actual_node
    ):
        return

    vm_migration_job_repo.create_or_update_pending_job(
        session=session,
        request_id=request.id,
        vmid=request.vmid,
        source_node=actual_node,
        target_node=desired_node,
        rebalance_epoch=int(request.rebalance_epoch or 0),
        last_error=None,
        requested_at=now,
        commit=False,
    )


def effective_request_migration_state(
    *,
    session: Session,
    request: VMRequest,
) -> tuple[VMMigrationStatus, str | None]:
    latest_job = vm_migration_job_repo.get_latest_job_for_request(
        session=session,
        request_id=request.id,
    )
    if latest_job is None:
        return request.migration_status, request.migration_error

    desired_node = str(request.desired_node or request.assigned_node or "")
    if (
        str(latest_job.target_node or "") != desired_node
        or int(latest_job.rebalance_epoch or 0) != int(request.rebalance_epoch or 0)
    ):
        return request.migration_status, request.migration_error

    mapped = {
        VMMigrationJobStatus.pending: VMMigrationStatus.pending,
        VMMigrationJobStatus.running: VMMigrationStatus.running,
        VMMigrationJobStatus.completed: VMMigrationStatus.completed,
        VMMigrationJobStatus.failed: VMMigrationStatus.failed,
        VMMigrationJobStatus.blocked: VMMigrationStatus.blocked,
        VMMigrationJobStatus.cancelled: request.migration_status,
    }
    return mapped.get(latest_job.status, request.migration_status), latest_job.last_error
