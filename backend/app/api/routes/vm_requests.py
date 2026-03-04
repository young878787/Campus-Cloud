"""VM Request API routes - 虛擬機申請與審核."""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.proxmox import basic_blocking_task_status, get_proxmox_api
from app.core.security import decrypt_value
from app.crud import audit_log as audit_log_crud
from app.crud import resource as resource_crud
from app.crud import vm_request as vm_request_crud
from app.models import (
    VMRequestCreate,
    VMRequestPublic,
    VMRequestReview,
    VMRequestStatus,
    VMRequestsPublic,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vm-requests", tags=["vm-requests"])


def _to_public(req, user_override=None) -> VMRequestPublic:
    """Convert VMRequest DB model to public schema with user info."""
    user = user_override or req.user
    return VMRequestPublic(
        id=req.id,
        user_id=req.user_id,
        user_email=user.email if user else None,
        user_full_name=user.full_name if user else None,
        reason=req.reason,
        resource_type=req.resource_type,
        hostname=req.hostname,
        cores=req.cores,
        memory=req.memory,
        storage=req.storage,
        environment_type=req.environment_type,
        os_info=req.os_info,
        expiry_date=req.expiry_date,
        ostemplate=req.ostemplate,
        rootfs_size=req.rootfs_size,
        template_id=req.template_id,
        disk_size=req.disk_size,
        username=req.username,
        status=req.status,
        reviewer_id=req.reviewer_id,
        review_comment=req.review_comment,
        reviewed_at=req.reviewed_at,
        vmid=req.vmid,
        created_at=req.created_at,
    )


@router.post("/", response_model=VMRequestPublic)
def create_vm_request(
    request_in: VMRequestCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Submit a new VM/LXC request (requires reason)."""
    if request_in.resource_type not in ("lxc", "vm"):
        raise HTTPException(
            status_code=400, detail="resource_type must be 'lxc' or 'vm'"
        )

    if request_in.resource_type == "lxc" and not request_in.ostemplate:
        raise HTTPException(
            status_code=400, detail="LXC request requires ostemplate"
        )

    if request_in.resource_type == "vm" and (
        not request_in.template_id or not request_in.username
    ):
        raise HTTPException(
            status_code=400,
            detail="VM request requires template_id and username",
        )

    db_request = vm_request_crud.create_vm_request(
        session=session,
        vm_request_in=request_in,
        user_id=current_user.id,
    )

    # Record audit log
    audit_log_crud.create_audit_log(
        session=session,
        user_id=current_user.id,
        vmid=None,  # No VMID yet
        action="vm_request_submit",
        details=f"Submitted {request_in.resource_type} request: {request_in.hostname}, {request_in.cores} cores, {request_in.memory}MB RAM. Reason: {request_in.reason}",
    )

    logger.info(
        f"User {current_user.email} submitted VM request {db_request.id}"
    )
    return _to_public(db_request, user_override=current_user)


@router.get("/my", response_model=VMRequestsPublic)
def list_my_vm_requests(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    """List the current user's VM requests."""
    requests, count = vm_request_crud.get_vm_requests_by_user(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )
    return VMRequestsPublic(
        data=[_to_public(r) for r in requests],
        count=count,
    )


@router.get("/", response_model=VMRequestsPublic)
def list_all_vm_requests(
    session: SessionDep,
    current_user: CurrentUser,
    status: VMRequestStatus | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    """List all VM requests (admin only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough privileges")

    requests, count = vm_request_crud.get_all_vm_requests(
        session=session, status=status, skip=skip, limit=limit
    )
    return VMRequestsPublic(
        data=[_to_public(r) for r in requests],
        count=count,
    )


@router.get("/{request_id}", response_model=VMRequestPublic)
def get_vm_request(
    request_id: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Get a single VM request."""
    import uuid

    try:
        req_uuid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID")

    db_request = vm_request_crud.get_vm_request_by_id(
        session=session, request_id=req_uuid
    )
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")

    # Users can only see their own requests; admins can see all
    if not current_user.is_superuser and db_request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough privileges")

    return _to_public(db_request)


@router.post("/{request_id}/review", response_model=VMRequestPublic)
def review_vm_request(
    request_id: str,
    review: VMRequestReview,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Approve or reject a VM request (admin only). If approved, auto-create the VM/LXC."""
    import uuid

    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough privileges")

    try:
        req_uuid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID")

    db_request = vm_request_crud.get_vm_request_by_id(
        session=session, request_id=req_uuid, for_update=True
    )
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")

    if db_request.status != VMRequestStatus.pending:
        raise HTTPException(
            status_code=400, detail="This request has already been reviewed"
        )

    vmid = None

    try:
        # If approved, create the VM/LXC automatically
        if review.status == VMRequestStatus.approved:
            vmid = _provision_resource(db_request, session)

        updated = vm_request_crud.update_vm_request_status(
            session=session,
            db_request=db_request,
            status=review.status,
            reviewer_id=current_user.id,
            review_comment=review.review_comment,
            vmid=vmid,
        )

        action = (
            "approved" if review.status == VMRequestStatus.approved else "rejected"
        )

        # Record audit log
        details = f"Reviewed VM request {request_id}: {action}"
        if review.status == VMRequestStatus.approved and vmid:
            details += f", created VMID {vmid}"
        if review.review_comment:
            details += f". Comment: {review.review_comment}"

        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=vmid,  # Will be None if rejected
            action="vm_request_review",
            details=details,
        )

        logger.info(
            f"Admin {current_user.email} {action} VM request {request_id}"
        )
    except Exception:
        logger.exception(
            "Failed to process review for VM request %s", request_id
        )

        # If provisioning failed after an approval attempt, reset the request
        # back to pending so that admins can retry or investigate.
        if review.status == VMRequestStatus.approved:
            error_comment = review.review_comment or ""
            if error_comment:
                error_comment += " | "
            error_comment += (
                "Automatic provisioning failed; please review and retry."
            )

            try:
                vm_request_crud.update_vm_request_status(
                    session=session,
                    db_request=db_request,
                    status=VMRequestStatus.pending,
                    reviewer_id=current_user.id,
                    review_comment=error_comment,
                    vmid=None,
                )
            except Exception:
                logger.exception(
                    "Failed to reset VM request %s back to pending "
                    "after provisioning error",
                    request_id,
                )

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to process review; automatic provisioning may have failed."
            ),
        )

    # Re-fetch with eager-loaded user relationship
    refreshed = vm_request_crud.get_vm_request_by_id(
        session=session, request_id=updated.id
    )
    return _to_public(refreshed)


def _provision_resource(db_request, session) -> int:
    """Provision a VM or LXC container based on an approved request."""
    proxmox = get_proxmox_api()
    new_vmid = proxmox.cluster.nextid.get()

    # Decrypt the stored password for Proxmox provisioning
    plain_password = decrypt_value(db_request.password)

    if db_request.resource_type == "lxc":
        config = {
            "vmid": new_vmid,
            "hostname": db_request.hostname,
            "ostemplate": db_request.ostemplate,
            "cores": db_request.cores,
            "memory": db_request.memory,
            "swap": 512,
            "rootfs": f"{settings.PROXMOX_DATA_STORAGE}:{db_request.rootfs_size or 8}",
            "password": plain_password,
            "net0": "name=eth0,bridge=vmbr0,ip=dhcp,firewall=0",
            "unprivileged": 1,
            "start": 1,
            "pool": "CampusCloud",
        }
        result = proxmox.nodes("pve").lxc.create(**config)
        basic_blocking_task_status("pve", result)

        resource_crud.create_resource(
            session=session,
            vmid=new_vmid,
            user_id=db_request.user_id,
            environment_type=db_request.environment_type,
            os_info=db_request.os_info,
            expiry_date=db_request.expiry_date,
            template_id=None,
        )
    else:
        # VM (QEMU) clone from template
        clone_config = {
            "newid": new_vmid,
            "name": db_request.hostname,
            "full": 1,
            "storage": settings.PROXMOX_DATA_STORAGE,
            "pool": "CampusCloud",
        }
        result = (
            proxmox.nodes("pve")
            .qemu(db_request.template_id)
            .clone.post(**clone_config)
        )
        basic_blocking_task_status("pve", result)

        config_updates = {
            "cores": db_request.cores,
            "memory": db_request.memory,
            "ciuser": db_request.username,
            "cipassword": plain_password,
            "sshkeys": "",
            "ciupgrade": 0,
        }
        proxmox.nodes("pve").qemu(new_vmid).config.put(**config_updates)

        if db_request.disk_size:
            proxmox.nodes("pve").qemu(new_vmid).resize.put(
                disk="scsi0", size=f"{db_request.disk_size}G"
            )

        # Auto-start the VM
        proxmox.nodes("pve").qemu(new_vmid).status.start.post()

        resource_crud.create_resource(
            session=session,
            vmid=new_vmid,
            user_id=db_request.user_id,
            environment_type=db_request.environment_type,
            os_info=db_request.os_info,
            expiry_date=db_request.expiry_date,
            template_id=db_request.template_id,
        )

    logger.info(f"Provisioned {db_request.resource_type} with VMID {new_vmid}")
    return new_vmid
