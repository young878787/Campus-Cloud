from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.db import engine
from app.exceptions import NotFoundError
from app.models import VMRequest, VMRequestStatus
from app.repositories import resource as resource_repo
from app.repositories import vm_request as vm_request_repo
from app.services import (
    audit_service,
    provisioning_service,
    proxmox_service,
)

logger = logging.getLogger(__name__)

SCHEDULER_POLL_SECONDS = 60


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _find_existing_resource_for_request(
    *,
    session: Session,
    request: VMRequest,
) -> dict | None:
    expected_type = "lxc" if request.resource_type == "lxc" else "qemu"
    claimed_vmids = {
        int(item.vmid)
        for item in session.exec(
            select(VMRequest).where(
                VMRequest.status == VMRequestStatus.approved,
                VMRequest.vmid.is_not(None),
                VMRequest.id != request.id,
            )
        ).all()
        if item.vmid is not None
    }
    for resource in proxmox_service.list_all_resources():
        if str(resource.get("type") or "") != expected_type:
            continue
        if str(resource.get("name") or "") != str(request.hostname or ""):
            continue
        vmid = int(resource.get("vmid"))
        if vmid in claimed_vmids:
            continue
        pool = str(resource.get("pool") or "")
        if pool and pool != "CampusCloud":
            continue
        return resource
    return None


def _adopt_or_provision_due_request(
    *,
    session: Session,
    request: VMRequest,
    resource_type: str,
) -> tuple[int, str | None, str | None, bool]:
    existing_resource = _find_existing_resource_for_request(
        session=session,
        request=request,
    )
    if existing_resource is not None:
        vmid = int(existing_resource["vmid"])
        assigned_node = str(existing_resource["node"])
        placement_strategy_used = (
            request.placement_strategy_used
            or "priority_dominant_share"
        )
        if not resource_repo.get_resource_by_vmid(
            session=session,
            vmid=vmid,
        ):
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
            assigned_node=assigned_node,
            placement_strategy_used=placement_strategy_used,
            commit=False,
        )
        status = proxmox_service.get_status(
            assigned_node,
            vmid,
            resource_type,
        )
        started = False
        if status.get("status") != "running":
            proxmox_service.control(
                assigned_node,
                vmid,
                resource_type,
                "start",
            )
            started = True
        audit_service.log_action(
            session=session,
            user_id=None,
            vmid=vmid,
            action="resource_start",
            details=(
                "Scheduled provisioning adopted an existing resource for approved "
                f"{request.resource_type} request {request.id}"
            ),
            commit=False,
        )
        logger.warning(
            "Adopted existing %s resource VMID %s for approved request %s",
            resource_type,
            vmid,
            request.id,
        )
        return vmid, assigned_node, placement_strategy_used, started

    vmid, assigned_node, placement_strategy_used = (
        provisioning_service.provision_from_request(
            session=session,
            db_request=request,
        )
    )
    vm_request_repo.update_vm_request_provisioning(
        session=session,
        db_request=request,
        vmid=vmid,
        assigned_node=assigned_node,
        placement_strategy_used=placement_strategy_used,
        commit=False,
    )
    audit_service.log_action(
        session=session,
        user_id=None,
        vmid=vmid,
        action=(
            "lxc_create"
            if request.resource_type == "lxc"
            else "vm_create"
        ),
        details=(
            "Scheduled provisioning completed for approved "
            f"{request.resource_type} request {request.id}"
            + (
                f" on node {assigned_node}"
                if assigned_node
                else ""
            )
        ),
        commit=False,
    )
    logger.info(
        "Auto-provisioned approved request %s with VMID %s",
        request.id,
        vmid,
    )
    return vmid, assigned_node, placement_strategy_used, True


def process_due_request_starts() -> int:
    started_count = 0
    changed = False
    now = _utc_now()

    with Session(engine) as session:
        due_requests = list(
            session.exec(
                select(VMRequest).where(
                    VMRequest.status == VMRequestStatus.approved,
                    VMRequest.start_at.is_not(None),
                    VMRequest.start_at <= now,
                )
            ).all()
        )
        due_requests.sort(
            key=lambda item: (
                item.vmid is None,
                item.start_at or datetime.min.replace(tzinfo=UTC),
                item.created_at or datetime.min.replace(tzinfo=UTC),
            )
        )

        for request in due_requests:
            if request.end_at:
                end_at = request.end_at
                if end_at.tzinfo is None:
                    end_at = end_at.replace(tzinfo=UTC)
                if end_at <= now:
                    continue

            provisioned_vmid: int | None = None
            stale_vmid: int | None = None
            try:
                vmid = request.vmid
                resource_type = "lxc" if request.resource_type == "lxc" else "qemu"

                if vmid is None:
                    vmid, _, _, was_started = _adopt_or_provision_due_request(
                        session=session,
                        request=request,
                        resource_type=resource_type,
                    )
                    provisioned_vmid = vmid
                    changed = True
                    started_count += 1
                    continue

                resource = proxmox_service.find_resource(vmid)
                if str(resource.get("name") or "") != str(request.hostname or ""):
                    stale_vmid = vmid
                    vm_request_repo.clear_vm_request_provisioning(
                        session=session,
                        db_request=request,
                        commit=False,
                    )
                    vmid, _, _, was_started = _adopt_or_provision_due_request(
                        session=session,
                        request=request,
                        resource_type=resource_type,
                    )
                    provisioned_vmid = vmid
                    changed = True
                    started_count += 1
                    logger.warning(
                        "Request %s had stale VMID %s mapped to hostname %s; reprovisioned as VMID %s",
                        request.id,
                        stale_vmid,
                        resource.get('name'),
                        vmid,
                    )
                    continue
                node = resource["node"]
                status = proxmox_service.get_status(node, vmid, resource_type)
                if status.get("status") == "running":
                    continue

                proxmox_service.control(node, vmid, resource_type, "start")
                audit_service.log_action(
                    session=session,
                    user_id=None,
                    vmid=vmid,
                    action="resource_start",
                    details=(
                        "Scheduled auto-start for approved "
                        f"{request.resource_type} request {request.id}"
                    ),
                    commit=False,
                )
                changed = True
                started_count += 1
                logger.info(
                    "Auto-started approved request %s on node %s with VMID %s",
                    request.id,
                    node,
                    vmid,
                )
            except NotFoundError:
                stale_vmid = request.vmid
                try:
                    if stale_vmid is not None:
                        vm_request_repo.clear_vm_request_provisioning(
                            session=session,
                            db_request=request,
                            commit=False,
                        )
                    vmid, _, _, was_started = _adopt_or_provision_due_request(
                        session=session,
                        request=request,
                        resource_type=resource_type,
                    )
                    provisioned_vmid = vmid
                    changed = True
                    started_count += 1
                    logger.warning(
                        "Recovered approved request %s from stale VMID %s; reprovisioned as VMID %s",
                        request.id,
                        stale_vmid,
                        vmid,
                    )
                except Exception:
                    logger.exception(
                        "Failed to recover approved request %s from stale VMID %s",
                        request.id,
                        stale_vmid,
                    )
            except Exception:
                if provisioned_vmid is not None:
                    try:
                        provisioning_service.cleanup_provisioned_resource(
                            provisioned_vmid
                        )
                    except Exception:
                        logger.exception(
                            "Failed to clean up scheduled provisioned resource %s for request %s",
                            provisioned_vmid,
                            request.id,
                        )
                logger.exception(
                    "Failed to auto-start/provision approved request %s with VMID %s",
                    request.id,
                    request.vmid,
                )

        if changed:
            session.commit()

    return started_count


def process_due_request_stops() -> int:
    stopped_count = 0
    now = _utc_now()

    with Session(engine) as session:
        due_requests = list(
            session.exec(
                select(VMRequest).where(
                    VMRequest.status == VMRequestStatus.approved,
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

            resource_type = "lxc" if request.resource_type == "lxc" else "qemu"

            try:
                resource = proxmox_service.find_resource(vmid)
                node = resource["node"]
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
                logger.warning(
                    "Scheduled shutdown skipped because resource %s was not found for request %s",
                    vmid,
                    request.id,
                )
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
    logger.info("VM request start scheduler is running")
    while not stop_event.is_set():
        try:
            process_due_request_starts()
            process_due_request_stops()
        except Exception:
            logger.exception("VM request start scheduler iteration failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SCHEDULER_POLL_SECONDS)
        except TimeoutError:
            continue

    logger.info("VM request start scheduler stopped")
