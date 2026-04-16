from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.core.db import engine
from app.domain.scheduling.models import ScheduledTask
from app.domain.scheduling.runner import run_polling_scheduler
from app.exceptions import NotFoundError
from app.infrastructure.proxmox import get_proxmox_settings
from app.models import (
    VMMigrationJob,
    VMMigrationJobStatus,
    VMMigrationStatus,
    VMRequest,
    VMRequestStatus,
)
from app.repositories import resource as resource_repo
from app.repositories import vm_migration_job as vm_migration_job_repo
from app.repositories import vm_request as vm_request_repo
from app.services.proxmox import provisioning_service, proxmox_service
from app.services.scheduling import policy as scheduling_policy
from app.services.scheduling import support as scheduling_support
from app.services.user import audit_service
from app.services.vm import vm_request_placement_service

logger = logging.getLogger(__name__)

SCHEDULER_POLL_SECONDS = scheduling_policy.SCHEDULER_POLL_SECONDS
_VM_DISK_PREFIXES = ("scsi", "sata", "ide", "virtio", "efidisk", "tpmstate")
_LXC_MOUNT_PREFIXES = ("rootfs", "mp")
_MigrationPolicy = scheduling_policy.MigrationPolicy


def _utc_now() -> datetime:
    return scheduling_policy.utc_now()


def _normalize_datetime(value: datetime | None) -> datetime | None:
    return scheduling_policy.normalize_datetime(value)


def _resource_type_for_request(request: VMRequest) -> str:
    return scheduling_policy.resource_type_for_request(request)


def _get_migration_policy(*, session: Session) -> _MigrationPolicy:
    return scheduling_policy.get_migration_policy(session=session)


def _migration_worker_id() -> str:
    return scheduling_policy.migration_worker_id()


def _next_retry_at(*, now: datetime, policy: _MigrationPolicy, attempt_count: int) -> datetime:
    return scheduling_policy.next_retry_at(
        now=now,
        policy=policy,
        attempt_count=attempt_count,
    )


def _find_existing_resource_for_request(
    *,
    session: Session,
    request: VMRequest,
) -> dict | None:
    return scheduling_support.find_existing_resource_for_request(
        session=session,
        request=request,
    )


def _adopt_existing_resource(
    *,
    session: Session,
    request: VMRequest,
) -> tuple[int, str, str | None, bool] | None:
    """Try to adopt an already-existing Proxmox resource for this request.

    Returns (vmid, actual_node, placement_strategy, started) or None.
    """
    resource_type = _resource_type_for_request(request)
    existing_resource = _find_existing_resource_for_request(
        session=session,
        request=request,
    )
    if existing_resource is None:
        return None

    desired_node = str(request.desired_node or request.assigned_node or "")
    placement_strategy_used = (
        request.placement_strategy_used
        or vm_request_placement_service.DEFAULT_PLACEMENT_STRATEGY
    )
    vmid = int(existing_resource["vmid"])
    actual_node = str(existing_resource["node"])
    if not resource_repo.get_resource_by_vmid(session=session, vmid=vmid):
        resource_repo.create_resource(
            session=session,
            vmid=vmid,
            user_id=request.user_id,
            environment_type=request.environment_type,
            os_info=request.os_info,
            expiry_date=request.expiry_date,
            template_id=request.template_id,
            commit=False,
        )
    vm_request_repo.update_vm_request_provisioning(
        session=session,
        db_request=request,
        vmid=vmid,
        assigned_node=desired_node or actual_node,
        desired_node=desired_node or actual_node,
        actual_node=actual_node,
        placement_strategy_used=placement_strategy_used,
        migration_status=(
            VMMigrationStatus.pending
            if desired_node and desired_node != actual_node
            else VMMigrationStatus.idle
        ),
        migration_error=None,
        commit=False,
    )
    request.status = VMRequestStatus.running
    session.add(request)

    status = proxmox_service.get_status(actual_node, vmid, resource_type)
    started = False
    if str(status.get("status") or "").lower() != "running":
        proxmox_service.control(actual_node, vmid, resource_type, "start")
        started = True
    audit_service.log_action(
        session=session,
        user_id=None,
        vmid=vmid,
        action="resource_start",
        details=(
            f"Adopted existing {request.resource_type} resource for request {request.id}"
        ),
        commit=False,
    )
    logger.warning(
        "Adopted existing %s resource VMID %s for request %s",
        resource_type, vmid, request.id,
    )
    # Detect if resource should be pinned
    try:
        pinned = _detect_migration_pinned(node=actual_node, vmid=vmid, resource_type=resource_type)
        if pinned and not request.migration_pinned:
            request.migration_pinned = True
            session.add(request)
    except Exception:
        logger.debug("Failed to detect migration pinning for VMID %s", vmid, exc_info=True)
    return vmid, actual_node, placement_strategy_used, started


def _provision_new_resource(
    *,
    session: Session,
    request: VMRequest,
) -> tuple[int, str, str | None]:
    """Lock → mark provisioning → clone outside txn → mark running.

    This is the core anti-duplication pattern:
    1. SELECT FOR UPDATE SKIP LOCKED — if locked, bail
    2. status = provisioning, commit  (visible to other sessions)
    3. plan_provision (resolve storage etc.)  — still in a short txn
    4. commit / close session
    5. execute_provision (clone VM) — NO open transaction
    6. Open new session → record vmid + status=running, commit
    """
    resource_type = _resource_type_for_request(request)
    desired_node = str(request.desired_node or request.assigned_node or "")

    # --- Phase 1: mark as provisioning + plan (short txn) -----------------
    request.status = VMRequestStatus.provisioning
    session.add(request)
    session.commit()
    logger.info("Marked request %s as provisioning", request.id)

    try:
        plan = provisioning_service.plan_provision(
            session=session,
            db_request=request,
        )
    except Exception:
        # Plan failed — revert to approved so scheduler can retry.
        request.status = VMRequestStatus.approved
        session.add(request)
        session.commit()
        raise

    request_id = request.id
    request_user_id = request.user_id
    request_env_type = request.environment_type
    request_os_info = request.os_info
    request_expiry_date = request.expiry_date
    request_template_id = request.template_id
    request_resource_type = request.resource_type
    request_migration_pinned = request.migration_pinned

    # Close session so clone runs outside any transaction.
    session.commit()

    # --- Phase 2: execute clone (NO open transaction) ---------------------
    try:
        new_vmid, actual_node = provisioning_service.execute_provision(plan)
    except Exception:
        # Clone failed — revert to approved.
        with Session(engine) as rollback_session:
            req = vm_request_repo.get_vm_request_by_id(
                session=rollback_session, request_id=request_id, for_update=True,
            )
            if req and req.status == VMRequestStatus.provisioning:
                req.status = VMRequestStatus.approved
                rollback_session.add(req)
                rollback_session.commit()
                logger.warning("Reverted request %s to approved after provision failure", request_id)
        raise

    # --- Phase 3: record result (new short txn) ---------------------------
    with Session(engine) as finish_session:
        req = vm_request_repo.get_vm_request_by_id(
            session=finish_session, request_id=request_id, for_update=True,
        )
        if req is None:
            logger.error("Request %s vanished after provisioning VMID %s", request_id, new_vmid)
            raise NotFoundError(f"Request {request_id} no longer exists")

        resource_repo.create_resource(
            session=finish_session,
            vmid=new_vmid,
            user_id=request_user_id,
            environment_type=request_env_type,
            os_info=request_os_info,
            expiry_date=request_expiry_date,
            template_id=request_template_id,
            ssh_private_key_encrypted=plan.get("ssh_private_key_encrypted"),
            ssh_public_key=plan.get("ssh_public_key"),
            commit=False,
        )
        vm_request_repo.update_vm_request_provisioning(
            session=finish_session,
            db_request=req,
            vmid=new_vmid,
            assigned_node=desired_node or actual_node,
            desired_node=desired_node or actual_node,
            actual_node=actual_node,
            placement_strategy_used=plan["placement_strategy"],
            migration_status=(
                VMMigrationStatus.pending
                if desired_node and desired_node != actual_node
                else VMMigrationStatus.completed
            ),
            migration_error=None,
            commit=False,
        )
        req.status = VMRequestStatus.running
        finish_session.add(req)

        audit_service.log_action(
            session=finish_session,
            user_id=None,
            vmid=new_vmid,
            action="lxc_create" if request_resource_type == "lxc" else "vm_create",
            details=f"Provisioned {request_resource_type} for request {request_id} on {actual_node}",
            commit=False,
        )
        # Detect if resource should be pinned
        try:
            pinned = _detect_migration_pinned(
                node=actual_node, vmid=new_vmid,
                resource_type="lxc" if request_resource_type == "lxc" else "qemu",
            )
            if pinned and not request_migration_pinned:
                req.migration_pinned = True
                finish_session.add(req)
        except Exception:
            logger.debug("Failed to detect migration pinning for VMID %s", new_vmid, exc_info=True)
        finish_session.commit()

    logger.info(
        "Provisioned request %s → VMID %s on node %s",
        request_id, new_vmid, actual_node,
    )
    return new_vmid, actual_node, plan["placement_strategy"]


def _mark_request_runtime_error(
    *,
    session: Session,
    request_id,
    message: str,
) -> None:
    scheduling_support.mark_request_runtime_error(
        session=session,
        request_id=request_id,
        message=message,
    )


def _refresh_actual_node(
    *,
    session: Session,
    request: VMRequest,
) -> tuple[str, dict]:
    db_request = vm_request_repo.get_vm_request_by_id(
        session=session,
        request_id=request.id,
        for_update=True,
    ) or request
    if request.vmid is None:
        raise NotFoundError(f"Request {request.id} has no provisioned VMID")
    resource = proxmox_service.find_resource(request.vmid)
    resource_name = str(resource.get("name") or "")
    # hostname is stored as punycode in DB since creation, so a direct
    # comparison is sufficient.
    expected_hostname = str(request.hostname or "")
    if resource_name != expected_hostname:
        raise NotFoundError(
            f"Provisioned resource {request.vmid} name '{resource_name}' "
            f"does not match request hostname '{expected_hostname}'"
        )
    actual_node = str(resource["node"])
    vm_request_repo.update_vm_request_provisioning(
        session=session,
        db_request=db_request,
        vmid=request.vmid,
        assigned_node=db_request.assigned_node,
        desired_node=db_request.desired_node,
        actual_node=actual_node,
        placement_strategy_used=db_request.placement_strategy_used,
        migration_status=(
            VMMigrationStatus.pending
            if db_request.desired_node and db_request.desired_node != actual_node
            else db_request.migration_status
        ),
        migration_error=(
            None
            if db_request.desired_node == actual_node
            else db_request.migration_error
        ),
        rebalance_epoch=db_request.rebalance_epoch,
        last_rebalanced_at=db_request.last_rebalanced_at,
        last_migrated_at=db_request.last_migrated_at,
        commit=False,
    )
    return actual_node, resource


def _extract_storage_id(config_value: object) -> str | None:
    return scheduling_support.extract_storage_id(config_value)


def _storage_ids_available_on_node(*, node: str) -> set[str]:
    return scheduling_support.storage_ids_available_on_node(node=node)


def _detect_migration_pinned(
    *,
    node: str,
    vmid: int,
    resource_type: str,
) -> bool:
    return scheduling_support.detect_migration_pinned(
        node=node,
        vmid=vmid,
        resource_type=resource_type,
    )


def _migration_block_reason(
    *,
    source_node: str,
    target_node: str,
    vmid: int,
    resource_type: str,
) -> str | None:
    return scheduling_support.migration_block_reason(
        source_node=source_node,
        target_node=target_node,
        vmid=vmid,
        resource_type=resource_type,
    )


def _sync_request_migration_job(
    *,
    session: Session,
    request: VMRequest,
    source_node: str | None,
    now: datetime,
) -> None:
    scheduling_support.sync_request_migration_job(
        session=session,
        request=request,
        source_node=source_node,
        now=now,
    )


def _effective_request_migration_state(
    *,
    session: Session,
    request: VMRequest,
) -> tuple[VMMigrationStatus, str | None]:
    return scheduling_support.effective_request_migration_state(
        session=session,
        request=request,
    )


def _migrate_request_to_desired_node(
    *,
    session: Session,
    request: VMRequest,
    current_node: str,
    now: datetime,
    policy: _MigrationPolicy,
    migrations_used: int,
    job: VMMigrationJob | None = None,
) -> tuple[str, bool]:
    desired_node = str(request.desired_node or request.assigned_node or "")
    if not desired_node or desired_node == current_node:
        return current_node, False
    if request.vmid is None:
        raise NotFoundError(f"Request {request.id} has no provisioned VMID")
    if not policy.enabled:
        defer_reason = "Migration deferred because automatic migration is disabled by system policy."
        if job is not None:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.pending,
                last_error=defer_reason,
                source_node=current_node,
                target_node=desired_node,
                vmid=request.vmid,
                available_at=now + timedelta(seconds=SCHEDULER_POLL_SECONDS),
                commit=False,
            )
        vm_request_repo.update_vm_request_provisioning(
            session=session,
            db_request=request,
            vmid=request.vmid,
            assigned_node=desired_node,
            desired_node=desired_node,
            actual_node=current_node,
            placement_strategy_used=request.placement_strategy_used,
            migration_status=VMMigrationStatus.pending,
            migration_error=defer_reason,
            rebalance_epoch=request.rebalance_epoch,
            last_rebalanced_at=request.last_rebalanced_at,
            last_migrated_at=request.last_migrated_at,
            commit=False,
        )
        return current_node, False
    if getattr(request, 'migration_pinned', False):
        block_reason = (
            "Migration blocked because this resource is pinned to its current node "
            "(hardware passthrough or local mount detected)."
        )
        if job is not None:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.blocked,
                last_error=block_reason,
                source_node=current_node,
                target_node=desired_node,
                vmid=request.vmid,
                finished_at=now,
                commit=False,
            )
        vm_request_repo.update_vm_request_provisioning(
            session=session,
            db_request=request,
            vmid=request.vmid,
            assigned_node=desired_node,
            desired_node=desired_node,
            actual_node=current_node,
            placement_strategy_used=request.placement_strategy_used,
            migration_status=VMMigrationStatus.blocked,
            migration_error=block_reason,
            rebalance_epoch=request.rebalance_epoch,
            last_rebalanced_at=request.last_rebalanced_at,
            last_migrated_at=request.last_migrated_at,
            commit=False,
        )
        logger.info(
            "Skipped pinned request %s VMID %s from %s to %s",
            request.id, request.vmid, current_node, desired_node,
        )
        return current_node, False
    if policy.max_per_rebalance <= migrations_used:
        defer_reason = (
            "Migration deferred because this rebalance window reached the migration budget."
        )
        if job is not None:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.pending,
                last_error=defer_reason,
                source_node=current_node,
                target_node=desired_node,
                vmid=request.vmid,
                available_at=now + timedelta(seconds=SCHEDULER_POLL_SECONDS),
                commit=False,
            )
        vm_request_repo.update_vm_request_provisioning(
            session=session,
            db_request=request,
            vmid=request.vmid,
            assigned_node=desired_node,
            desired_node=desired_node,
            actual_node=current_node,
            placement_strategy_used=request.placement_strategy_used,
            migration_status=VMMigrationStatus.pending,
            migration_error=defer_reason,
            rebalance_epoch=request.rebalance_epoch,
            last_rebalanced_at=request.last_rebalanced_at,
            last_migrated_at=request.last_migrated_at,
            commit=False,
        )
        return current_node, False
    last_migrated_at = _normalize_datetime(request.last_migrated_at)
    if (
        last_migrated_at is not None
        and policy.min_interval_minutes > 0
        and now - last_migrated_at < timedelta(minutes=policy.min_interval_minutes)
    ):
        defer_reason = (
            "Migration deferred because this request was migrated too recently."
        )
        if job is not None:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.pending,
                last_error=defer_reason,
                source_node=current_node,
                target_node=desired_node,
                vmid=request.vmid,
                available_at=last_migrated_at + timedelta(minutes=policy.min_interval_minutes),
                commit=False,
            )
        vm_request_repo.update_vm_request_provisioning(
            session=session,
            db_request=request,
            vmid=request.vmid,
            assigned_node=desired_node,
            desired_node=desired_node,
            actual_node=current_node,
            placement_strategy_used=request.placement_strategy_used,
            migration_status=VMMigrationStatus.pending,
            migration_error=defer_reason,
            rebalance_epoch=request.rebalance_epoch,
            last_rebalanced_at=request.last_rebalanced_at,
            last_migrated_at=request.last_migrated_at,
            commit=False,
        )
        return current_node, False

    resource_type = _resource_type_for_request(request)
    current_status = proxmox_service.get_status(
        current_node,
        request.vmid,
        resource_type,
    )
    online = str(current_status.get("status") or "").lower() == "running"

    if resource_type == "lxc" and online and not policy.lxc_live_enabled:
        block_reason = (
            "Migration blocked because LXC live migration is disabled. "
            "The container must be stopped before migrating, or enable "
            "migration_lxc_live_enabled in system settings."
        )
        if job is not None:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.blocked,
                last_error=block_reason,
                source_node=current_node,
                target_node=desired_node,
                vmid=request.vmid,
                finished_at=now,
                commit=False,
            )
        vm_request_repo.update_vm_request_provisioning(
            session=session,
            db_request=request,
            vmid=request.vmid,
            assigned_node=desired_node,
            desired_node=desired_node,
            actual_node=current_node,
            placement_strategy_used=request.placement_strategy_used,
            migration_status=VMMigrationStatus.blocked,
            migration_error=block_reason,
            rebalance_epoch=request.rebalance_epoch,
            last_rebalanced_at=request.last_rebalanced_at,
            last_migrated_at=request.last_migrated_at,
            commit=False,
        )
        logger.warning(
            "Blocked LXC live migration for request %s VMID %s from %s to %s",
            request.id,
            request.vmid,
            current_node,
            desired_node,
        )
        return current_node, False

    block_reason = _migration_block_reason(
        source_node=current_node,
        target_node=desired_node,
        vmid=request.vmid,
        resource_type=resource_type,
    )
    if block_reason:
        if job is not None:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.blocked,
                last_error=block_reason,
                source_node=current_node,
                target_node=desired_node,
                vmid=request.vmid,
                finished_at=now,
                commit=False,
            )
        vm_request_repo.update_vm_request_provisioning(
            session=session,
            db_request=request,
            vmid=request.vmid,
            assigned_node=desired_node,
            desired_node=desired_node,
            actual_node=current_node,
            placement_strategy_used=request.placement_strategy_used,
            migration_status=VMMigrationStatus.blocked,
            migration_error=block_reason,
            rebalance_epoch=request.rebalance_epoch,
            last_rebalanced_at=request.last_rebalanced_at,
            last_migrated_at=request.last_migrated_at,
            commit=False,
        )
        logger.warning(
            "Blocked migration for request %s VMID %s from %s to %s: %s",
            request.id,
            request.vmid,
            current_node,
            desired_node,
            block_reason,
        )
        return current_node, False
    started_at = _utc_now()
    if job is not None:
        vm_migration_job_repo.update_job_status(
            session=session,
            job=job,
            status=VMMigrationJobStatus.running,
            last_error=None,
            attempt_delta=1,
            available_at=None,
            started_at=started_at,
            source_node=current_node,
            target_node=desired_node,
            vmid=request.vmid,
            commit=False,
        )
    vm_request_repo.update_vm_request_provisioning(
        session=session,
        db_request=request,
        vmid=request.vmid,
        assigned_node=desired_node,
        desired_node=desired_node,
        actual_node=current_node,
        placement_strategy_used=request.placement_strategy_used,
        migration_status=VMMigrationStatus.running,
        migration_error=None,
        rebalance_epoch=request.rebalance_epoch,
        last_rebalanced_at=request.last_rebalanced_at,
        last_migrated_at=request.last_migrated_at,
        commit=False,
    )
    claim_refresh_interval_seconds = max(
        5,
        min(
            max(int(policy.claim_timeout_seconds or 0) // 3, 5),
            30,
        ),
    )
    last_claim_refresh = time.monotonic()

    def _heartbeat(_: dict) -> None:
        nonlocal last_claim_refresh
        if job is None:
            return
        if (time.monotonic() - last_claim_refresh) < claim_refresh_interval_seconds:
            return
        vm_migration_job_repo.extend_job_claim(
            session=session,
            job=job,
            now=_utc_now(),
            claim_timeout_seconds=policy.claim_timeout_seconds,
            commit=True,
        )
        last_claim_refresh = time.monotonic()

    if job is not None:
        session.commit()
    proxmox_service.migrate_resource(
        current_node,
        desired_node,
        request.vmid,
        resource_type,
        online=online,
        progress_callback=_heartbeat if job is not None else None,
    )
    migrated_resource = proxmox_service.find_resource(request.vmid)
    new_actual_node = str(migrated_resource["node"])
    finished_at = _utc_now()
    if job is not None:
        vm_migration_job_repo.update_job_status(
            session=session,
            job=job,
            status=(
                VMMigrationJobStatus.completed
                if new_actual_node == desired_node
                else VMMigrationJobStatus.blocked
            ),
            last_error=(
                None
                if new_actual_node == desired_node
                else f"Migration finished on unexpected node {new_actual_node}"
            ),
            source_node=current_node,
            target_node=desired_node,
            vmid=request.vmid,
            finished_at=finished_at,
            commit=False,
        )
    vm_request_repo.update_vm_request_provisioning(
        session=session,
        db_request=request,
        vmid=request.vmid,
        assigned_node=desired_node,
        desired_node=desired_node,
        actual_node=new_actual_node,
        placement_strategy_used=request.placement_strategy_used,
        migration_status=(
            VMMigrationStatus.completed
            if new_actual_node == desired_node
            else VMMigrationStatus.blocked
        ),
        migration_error=(
            None
            if new_actual_node == desired_node
            else f"Migration finished on unexpected node {new_actual_node}"
        ),
        rebalance_epoch=request.rebalance_epoch,
        last_rebalanced_at=request.last_rebalanced_at,
        last_migrated_at=(
            finished_at if new_actual_node == desired_node else request.last_migrated_at
        ),
        commit=False,
    )
    audit_service.log_action(
        session=session,
        user_id=None,
        vmid=request.vmid,
        action="resource_migrate",
        details=(
            f"Auto-rebalanced request {request.id} from {current_node} "
            f"to {new_actual_node} for active time slot balancing"
        ),
        commit=False,
    )
    logger.info(
        "Migrated request %s VMID %s from %s to %s",
        request.id,
        request.vmid,
        current_node,
        new_actual_node,
    )
    return new_actual_node, new_actual_node == desired_node


def _process_pending_migration_jobs(
    *,
    session: Session,
    now: datetime,
    policy: _MigrationPolicy,
    active_requests: list[VMRequest],
) -> int:
    request_ids = [request.id for request in active_requests]
    claimed_jobs = vm_migration_job_repo.claim_jobs_for_requests(
        session=session,
        request_ids=request_ids,
        worker_id=_migration_worker_id(),
        now=now,
        limit=policy.worker_concurrency,
        claim_timeout_seconds=policy.claim_timeout_seconds,
    )
    if not claimed_jobs:
        return 0
    session.commit()

    migrations_used = 0
    active_request_map = {request.id: request for request in active_requests}
    for job in claimed_jobs:
        request = vm_request_repo.get_vm_request_by_id(
            session=session,
            request_id=job.request_id,
            for_update=True,
        )
        if request is None:
            deleted_jobs = vm_migration_job_repo.delete_jobs_for_request(
                session=session,
                request_id=job.request_id,
                commit=False,
            )
            logger.warning(
                "Deleted %s orphaned migration job(s) for missing request %s",
                deleted_jobs,
                job.request_id,
            )
            session.commit()
            continue
        if request.id not in active_request_map:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.cancelled,
                last_error="Migration queue entry was cancelled because the request is no longer active.",
                finished_at=now,
                commit=False,
            )
            session.commit()
            continue

        try:
            actual_node, _ = _refresh_actual_node(
                session=session,
                request=request,
            )
        except NotFoundError:
            stale_vmid = request.vmid
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.failed,
                last_error=(
                    f"Migration queue entry failed because VMID {stale_vmid} is stale."
                ),
                attempt_delta=1,
                finished_at=now,
                available_at=None,
                commit=False,
            )
            vm_request_repo.clear_vm_request_provisioning(
                session=session,
                db_request=request,
                commit=False,
            )
            session.commit()
            continue

        desired_node = str(request.desired_node or request.assigned_node or "")
        if not desired_node or desired_node == actual_node:
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=VMMigrationJobStatus.completed,
                last_error=None,
                source_node=actual_node,
                target_node=desired_node or actual_node,
                vmid=request.vmid,
                finished_at=now,
                available_at=None,
                commit=False,
            )
            vm_request_repo.update_vm_request_provisioning(
                session=session,
                db_request=request,
                vmid=request.vmid,
                assigned_node=desired_node or actual_node,
                desired_node=desired_node or actual_node,
                actual_node=actual_node,
                placement_strategy_used=request.placement_strategy_used,
                migration_status=VMMigrationStatus.completed,
                migration_error=None,
                rebalance_epoch=request.rebalance_epoch,
                last_rebalanced_at=request.last_rebalanced_at,
                last_migrated_at=request.last_migrated_at,
                commit=False,
            )
            session.commit()
            continue

        try:
            _, migrated = _migrate_request_to_desired_node(
                session=session,
                request=request,
                current_node=actual_node,
                now=now,
                policy=policy,
                migrations_used=migrations_used,
                job=job,
            )
            if migrated:
                migrations_used += 1
            session.commit()
        except Exception as exc:
            exceeded_retry_limit = int(job.attempt_count or 0) >= policy.retry_limit > 0
            new_status = (
                VMMigrationJobStatus.failed
                if exceeded_retry_limit
                else VMMigrationJobStatus.pending
            )
            vm_migration_job_repo.update_job_status(
                session=session,
                job=job,
                status=new_status,
                last_error=str(exc)[:500],
                source_node=actual_node,
                target_node=desired_node,
                vmid=request.vmid,
                finished_at=now if new_status == VMMigrationJobStatus.failed else None,
                available_at=(
                    None
                    if new_status == VMMigrationJobStatus.failed
                    else _next_retry_at(
                        now=now,
                        policy=policy,
                        attempt_count=int(job.attempt_count or 0),
                    )
                ),
                commit=False,
            )
            vm_request_repo.update_vm_request_provisioning(
                session=session,
                db_request=request,
                vmid=request.vmid,
                assigned_node=desired_node,
                desired_node=desired_node,
                actual_node=actual_node,
                placement_strategy_used=request.placement_strategy_used,
                migration_status=(
                    VMMigrationStatus.failed
                    if new_status == VMMigrationJobStatus.failed
                    else VMMigrationStatus.pending
                ),
                migration_error=str(exc)[:500],
                rebalance_epoch=request.rebalance_epoch,
                last_rebalanced_at=request.last_rebalanced_at,
                last_migrated_at=request.last_migrated_at,
                commit=False,
            )
            logger.exception(
                "Failed to process migration job %s for request %s",
                job.id,
                request.id,
            )
            session.commit()

    return migrations_used


def _ensure_request_running(
    *,
    session: Session,
    request: VMRequest,
    now: datetime,
    policy: _MigrationPolicy,
    migrations_used: int,
) -> tuple[bool, int]:
    """Make sure an approved/running request has a live VM.

    For requests without a vmid: lock → mark provisioning → clone → mark running.
    For requests with a vmid: ensure the VM is started.
    """
    resource_type = _resource_type_for_request(request)

    # ---- No VMID yet → need to provision ---------------------------------
    if request.vmid is None:
        # SELECT FOR UPDATE SKIP LOCKED — skip if another session holds it.
        locked = vm_request_repo.get_vm_request_by_id(
            session=session,
            request_id=request.id,
            for_update=True,
            skip_locked=True,
        )
        if locked is None:
            return False, migrations_used
        # Re-check: another process may have set vmid or changed status.
        if locked.vmid is not None or locked.status == VMRequestStatus.provisioning:
            return False, migrations_used

        # Try adopting an existing Proxmox resource first.
        adopted = _adopt_existing_resource(session=session, request=locked)
        if adopted is not None:
            vmid, actual_node, strategy, started = adopted
            session.commit()
            return started, migrations_used

        # Full provision: mark provisioning → clone outside txn → mark running.
        # _provision_new_resource manages its own sessions/commits.
        _provision_new_resource(session=session, request=locked)
        refreshed = vm_request_repo.get_vm_request_by_id(
            session=session,
            request_id=locked.id,
        )
        started = bool(
            refreshed is not None
            and refreshed.vmid is not None
            and refreshed.status in (
                VMRequestStatus.provisioning,
                VMRequestStatus.running,
            )
        )
        return started, migrations_used

    # ---- Already provisioned → ensure VM is started ----------------------
    actual_node, _ = _refresh_actual_node(session=session, request=request)
    _sync_request_migration_job(
        session=session, request=request, source_node=actual_node, now=now,
    )
    request = vm_request_repo.get_vm_request_by_id(
        session=session, request_id=request.id, for_update=True,
    ) or request
    effective_migration_status, effective_migration_error = _effective_request_migration_state(
        session=session, request=request,
    )

    pve_status = proxmox_service.get_status(actual_node, request.vmid, resource_type)
    is_running = str(pve_status.get("status") or "").lower() == "running"
    if not is_running:
        proxmox_service.control(actual_node, request.vmid, resource_type, "start")

    # Ensure status is 'running' in DB.
    if request.status != VMRequestStatus.running:
        request.status = VMRequestStatus.running
        session.add(request)
    vm_request_repo.update_vm_request_provisioning(
        session=session,
        db_request=request,
        vmid=request.vmid,
        assigned_node=request.desired_node or actual_node,
        desired_node=request.desired_node or actual_node,
        actual_node=actual_node,
        placement_strategy_used=request.placement_strategy_used,
        migration_status=(
            VMMigrationStatus.completed
            if request.desired_node and request.desired_node == actual_node
            else effective_migration_status
        ),
        migration_error=(
            None
            if request.desired_node and request.desired_node == actual_node
            else effective_migration_error
        ),
        rebalance_epoch=request.rebalance_epoch,
        last_rebalanced_at=request.last_rebalanced_at,
        last_migrated_at=request.last_migrated_at,
        commit=False,
    )
    if not is_running:
        audit_service.log_action(
            session=session,
            user_id=None,
            vmid=request.vmid,
            action="resource_start",
            details=f"Auto-started {request.resource_type} request {request.id}",
            commit=False,
        )
        logger.info(
            "Auto-started request %s on node %s with VMID %s",
            request.id, actual_node, request.vmid,
        )
    return not is_running, migrations_used


def _rebalance_active_window(now: datetime) -> int:
    with Session(engine) as session:
        due_requests = vm_request_repo.list_due_for_rebalance_vm_requests(
            session=session,
            at_time=now,
        )
        if not due_requests:
            return 0

        active_requests = vm_request_repo.list_active_approved_vm_requests(
            session=session,
            at_time=now,
        )
        if not active_requests:
            return 0

        selections = vm_request_placement_service.rebalance_active_assignments(
            session=session,
            requests=active_requests,
        )
        rebalance_epoch = max(
            (int(item.rebalance_epoch or 0) for item in active_requests),
            default=0,
        ) + 1

        for request in active_requests:
            selection = selections.get(request.id)
            if not selection or not selection.node:
                raise ValueError(
                    f"No feasible active placement exists for request {request.id}"
                )
            known_actual_node = request.actual_node
            if request.vmid is not None and not known_actual_node:
                known_actual_node = request.assigned_node
            vm_request_repo.update_vm_request_provisioning(
                session=session,
                db_request=request,
                vmid=request.vmid,
                assigned_node=selection.node,
                desired_node=selection.node,
                actual_node=known_actual_node,
                placement_strategy_used=selection.strategy,
                migration_status=(
                    VMMigrationStatus.pending
                    if request.vmid is not None
                    and known_actual_node
                    and known_actual_node != selection.node
                    else VMMigrationStatus.idle
                ),
                migration_error=None,
                rebalance_epoch=rebalance_epoch,
                last_rebalanced_at=now,
                commit=False,
            )
            _sync_request_migration_job(
                session=session,
                request=request,
                source_node=known_actual_node,
                now=now,
            )
        session.commit()
        return len(due_requests)


def process_single_request_start(request_id: uuid.UUID) -> bool:
    """Immediately trigger provisioning for a single approved request."""
    now = _utc_now()
    with Session(engine) as session:
        policy = _get_migration_policy(session=session)
        request = vm_request_repo.get_vm_request_by_id(
            session=session,
            request_id=request_id,
            for_update=True,
            skip_locked=True,
        )
        if not request or request.status not in (
            VMRequestStatus.approved,
            VMRequestStatus.running,
        ):
            return False
        try:
            started, _ = _ensure_request_running(
                session=session,
                request=request,
                now=now,
                policy=policy,
                migrations_used=0,
            )
            session.commit()
            return started
        except Exception:
            session.rollback()
            logger.exception(
                "Failed to immediately provision request %s", request_id
            )
            return False


def process_due_request_starts() -> int:
    started_count = 0
    now = _utc_now()

    try:
        _rebalance_active_window(now)
    except ValueError:
        logger.exception("Failed to rebalance active VM request window")
    except Exception:
        logger.exception("Unexpected error while rebalancing active VM request window")

    with Session(engine) as session:
        policy = _get_migration_policy(session=session)
        active_requests = vm_request_repo.list_active_approved_vm_requests(
            session=session,
            at_time=now,
        )
        migrations_used = _process_pending_migration_jobs(
            session=session,
            now=now,
            policy=policy,
            active_requests=active_requests,
        )

        for request in active_requests:
            try:
                started, migrations_used = _ensure_request_running(
                    session=session,
                    request=request,
                    now=now,
                    policy=policy,
                    migrations_used=migrations_used,
                )
                if started:
                    started_count += 1
                session.commit()
            except NotFoundError:
                stale_vmid = request.vmid
                session.rollback()
                # Retry find_resource up to 3 times with a short delay
                # to tolerate transient Proxmox API hiccups.
                if stale_vmid is not None:
                    confirmed_gone = True
                    for attempt in range(3):
                        try:
                            proxmox_service.find_resource(stale_vmid)
                            confirmed_gone = False
                            break
                        except NotFoundError:
                            if attempt < 2:
                                time.sleep(2)
                    if not confirmed_gone:
                        logger.info(
                            "VMID %s still exists on Proxmox; "
                            "skipping recovery for request %s",
                            stale_vmid, request.id,
                        )
                        continue
                # VMID confirmed absent — clear and re-provision.
                try:
                    if stale_vmid is not None:
                        vm_request_repo.clear_vm_request_provisioning(
                            session=session,
                            db_request=request,
                            commit=False,
                        )
                        request.status = VMRequestStatus.approved
                        session.add(request)
                        session.commit()
                    started, migrations_used = _ensure_request_running(
                        session=session,
                        request=request,
                        now=now,
                        policy=policy,
                        migrations_used=migrations_used,
                    )
                    if started:
                        started_count += 1
                    session.commit()
                    logger.warning(
                        "Recovered request %s from stale VMID %s",
                        request.id, stale_vmid,
                    )
                except Exception as exc:
                    session.rollback()
                    _mark_request_runtime_error(
                        session=session,
                        request_id=request.id,
                        message=str(exc),
                    )
                    logger.exception(
                        "Failed to recover request %s from stale VMID %s",
                        request.id, stale_vmid,
                    )
            except Exception as exc:
                session.rollback()
                _mark_request_runtime_error(
                    session=session,
                    request_id=request.id,
                    message=str(exc),
                )
                logger.exception(
                    "Failed to reconcile approved request %s with VMID %s",
                    request.id,
                    request.vmid,
                )

    return started_count


def process_due_request_stops() -> int:
    stopped_count = 0
    now = _utc_now()

    with Session(engine) as session:
        _stop_statuses = (
            VMRequestStatus.approved,
            VMRequestStatus.provisioning,
            VMRequestStatus.running,
        )
        due_requests = list(
            session.exec(
                select(VMRequest).where(
                    VMRequest.status.in_(_stop_statuses),
                    VMRequest.vmid.is_not(None),
                    VMRequest.end_at.is_not(None),
                    VMRequest.end_at <= now,
                )
            ).all()
        )

        for request in due_requests:
            vmid = request.vmid
            if vmid is None:
                continue

            resource_type = _resource_type_for_request(request)

            try:
                resource = proxmox_service.find_resource(vmid)
                node = str(resource["node"])
                status = proxmox_service.get_status(node, vmid, resource_type)
                current_status = str(status.get("status") or "").lower()
                if current_status in {"stopped", "paused"}:
                    continue

                proxmox_service.control(node, vmid, resource_type, "shutdown")
                audit_service.log_action(
                    session=session,
                    user_id=None,
                    vmid=vmid,
                    action="resource_shutdown",
                    details=(
                        "Scheduled auto-shutdown for approved "
                        f"{request.resource_type} request {request.id}"
                    ),
                    commit=False,
                )
                stopped_count += 1
                logger.info(
                    "Auto-shutdown triggered for approved request %s on node %s with VMID %s",
                    request.id,
                    node,
                    vmid,
                )
            except NotFoundError:
                logger.debug(
                    "Scheduled shutdown skipped: resource %s not found for request %s, clearing vmid",
                    vmid,
                    request.id,
                )
                request.vmid = None
                session.add(request)
                session.commit()
            except Exception:
                logger.exception(
                    "Failed to auto-shutdown approved request %s with VMID %s",
                    request.id,
                    vmid,
                )

        if stopped_count > 0:
            session.commit()

    return stopped_count


async def run_scheduler(stop_event: asyncio.Event) -> None:
    logger.info("VM request scheduler is running")
    await run_polling_scheduler(
        stop_event=stop_event,
        interval_seconds=SCHEDULER_POLL_SECONDS,
        tasks=[
            ScheduledTask(name="process_due_request_starts", handler=process_due_request_starts),
            ScheduledTask(name="process_due_request_stops", handler=process_due_request_stops),
        ],
    )
    logger.info("VM request scheduler stopped")
