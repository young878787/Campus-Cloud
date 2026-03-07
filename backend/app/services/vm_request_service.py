import logging
import uuid

from sqlmodel import Session

from app.core.security import encrypt_value
from app.exceptions import (
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    ProvisioningError,
)
from app.models import VMRequest, VMRequestStatus
from app.schemas import (
    VMRequestCreate,
    VMRequestPublic,
    VMRequestReview,
    VMRequestsPublic,
)
from app.repositories import vm_request as vm_request_repo
from app.services import audit_service, provisioning_service

logger = logging.getLogger(__name__)


def _to_public(req: VMRequest, user_override=None) -> VMRequestPublic:
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


def create(
    *, session: Session, request_in: VMRequestCreate, user
) -> VMRequestPublic:
    if request_in.resource_type not in ("lxc", "vm"):
        raise BadRequestError("resource_type must be 'lxc' or 'vm'")
    if request_in.resource_type == "lxc" and not request_in.ostemplate:
        raise BadRequestError("LXC request requires ostemplate")
    if request_in.resource_type == "vm" and (
        not request_in.template_id or not request_in.username
    ):
        raise BadRequestError("VM request requires template_id and username")

    db_request = vm_request_repo.create_vm_request(
        session=session,
        vm_request_in=request_in,
        user_id=user.id,
        encrypted_password=encrypt_value(request_in.password),
    )

    audit_service.log_action(
        session=session,
        user_id=user.id,
        action="vm_request_submit",
        details=(
            f"Submitted {request_in.resource_type} request: {request_in.hostname}, "
            f"{request_in.cores} cores, {request_in.memory}MB RAM. "
            f"Reason: {request_in.reason}"
        ),
    )

    logger.info(f"User {user.email} submitted VM request {db_request.id}")
    return _to_public(db_request, user_override=user)


def list_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> VMRequestsPublic:
    requests, count = vm_request_repo.get_vm_requests_by_user(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    return VMRequestsPublic(
        data=[_to_public(r) for r in requests], count=count
    )


def list_all(
    *,
    session: Session,
    status: VMRequestStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> VMRequestsPublic:
    requests, count = vm_request_repo.get_all_vm_requests(
        session=session, status=status, skip=skip, limit=limit
    )
    return VMRequestsPublic(
        data=[_to_public(r) for r in requests], count=count
    )


def get(
    *, session: Session, request_id: uuid.UUID, current_user
) -> VMRequestPublic:
    db_request = vm_request_repo.get_vm_request_by_id(
        session=session, request_id=request_id
    )
    if not db_request:
        raise NotFoundError("Request not found")
    if not current_user.is_superuser and db_request.user_id != current_user.id:
        raise PermissionDeniedError("Not enough privileges")
    return _to_public(db_request)


def review(
    *,
    session: Session,
    request_id: uuid.UUID,
    review_data: VMRequestReview,
    reviewer,
) -> VMRequestPublic:
    db_request = vm_request_repo.get_vm_request_by_id(
        session=session, request_id=request_id, for_update=True
    )
    if not db_request:
        raise NotFoundError("Request not found")
    if db_request.status != VMRequestStatus.pending:
        raise BadRequestError("This request has already been reviewed")

    vmid = None

    try:
        if review_data.status == VMRequestStatus.approved:
            vmid = provisioning_service.provision_from_request(
                session=session, db_request=db_request
            )

        updated = vm_request_repo.update_vm_request_status(
            session=session,
            db_request=db_request,
            status=review_data.status,
            reviewer_id=reviewer.id,
            review_comment=review_data.review_comment,
            vmid=vmid,
        )

        action = (
            "approved"
            if review_data.status == VMRequestStatus.approved
            else "rejected"
        )
        details = f"Reviewed VM request {request_id}: {action}"
        if review_data.status == VMRequestStatus.approved and vmid:
            details += f", created VMID {vmid}"
        if review_data.review_comment:
            details += f". Comment: {review_data.review_comment}"

        audit_service.log_action(
            session=session,
            user_id=reviewer.id,
            vmid=vmid,
            action="vm_request_review",
            details=details,
        )

        logger.info(
            f"Admin {reviewer.email} {action} VM request {request_id}"
        )
    except Exception:
        logger.exception(
            "Failed to process review for VM request %s", request_id
        )

        # Reset to pending on provisioning failure
        if review_data.status == VMRequestStatus.approved:
            error_comment = review_data.review_comment or ""
            if error_comment:
                error_comment += " | "
            error_comment += (
                "Automatic provisioning failed; please review and retry."
            )

            try:
                vm_request_repo.update_vm_request_status(
                    session=session,
                    db_request=db_request,
                    status=VMRequestStatus.pending,
                    reviewer_id=reviewer.id,
                    review_comment=error_comment,
                    vmid=None,
                )
            except Exception:
                logger.exception(
                    "Failed to reset VM request %s back to pending",
                    request_id,
                )

        raise ProvisioningError(
            "Failed to process review; automatic provisioning may have failed."
        )

    refreshed = vm_request_repo.get_vm_request_by_id(
        session=session, request_id=updated.id
    )
    return _to_public(refreshed)
