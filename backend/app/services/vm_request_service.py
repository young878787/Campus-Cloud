import logging
import uuid
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.security import encrypt_value
from app.exceptions import (
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    ProvisioningError,
)
from app.models import UserRole, VMRequest, VMRequestStatus
from app.schemas import (
    VMRequestCreate,
    VMRequestPublic,
    VMRequestReview,
    VMRequestsPublic,
)
from app.repositories import vm_request as vm_request_repo
from app.services import (
    audit_service,
    vm_request_availability_service,
    vm_request_placement_service,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
        start_at=req.start_at,
        end_at=req.end_at,
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
        assigned_node=req.assigned_node,
        placement_strategy_used=req.placement_strategy_used,
        created_at=req.created_at,
    )


def create(
    *, session: Session, request_in: VMRequestCreate, user
) -> VMRequestPublic:
    if getattr(user, "role", None) != UserRole.student:
        raise PermissionDeniedError("Only students can submit VM requests")

    if request_in.resource_type not in ("lxc", "vm"):
        raise BadRequestError("resource_type must be 'lxc' or 'vm'")
    if request_in.resource_type == "lxc" and not request_in.ostemplate:
        raise BadRequestError("LXC request requires ostemplate")
    if request_in.resource_type == "vm" and (
        not request_in.template_id or not request_in.username
    ):
        raise BadRequestError("VM request requires template_id and username")
    if request_in.end_at <= request_in.start_at:
        raise BadRequestError("end_at must be later than start_at")
    vm_request_availability_service.validate_request_window(
        session=session,
        current_user=user,
        request_in=request_in,
    )

    db_request = vm_request_repo.create_vm_request(
        session=session,
        vm_request_in=request_in,
        user_id=user.id,
        encrypted_password=encrypt_value(request_in.password),
        commit=False,
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
        commit=False,
    )
    session.commit()

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

    reservation = None
    try:
        if review_data.status == VMRequestStatus.approved:
            if not db_request.start_at or not db_request.end_at:
                raise BadRequestError(
                    "A scheduled request window is required before approval."
                )
            start_at = db_request.start_at
            end_at = db_request.end_at
            if start_at.tzinfo is None:
                start_at = start_at.replace(tzinfo=UTC)
            if end_at.tzinfo is None:
                end_at = end_at.replace(tzinfo=UTC)
            if end_at <= _utc_now():
                raise BadRequestError(
                    "This request window has already ended and can no longer be approved."
                )
            locked_requests = vm_request_repo.lock_overlapping_vm_requests_for_window(
                session=session,
                window_start=start_at,
                window_end=end_at,
            )
        else:
            locked_requests = []
        updated = vm_request_repo.update_vm_request_status(
            session=session,
            db_request=db_request,
            status=review_data.status,
            reviewer_id=reviewer.id,
            review_comment=review_data.review_comment,
            assigned_node=None,
            placement_strategy_used=None,
            commit=False,
        )

        if review_data.status == VMRequestStatus.approved:
            approved_requests = [
                item
                for item in locked_requests
                if item.id != updated.id and item.status == VMRequestStatus.approved
            ]
            approved_requests.append(updated)

            selections = vm_request_placement_service.rebuild_reserved_assignments(
                session=session,
                requests=approved_requests,
            )
            for request in approved_requests:
                selection = selections.get(request.id)
                if not selection or not selection.node:
                    raise BadRequestError(
                        "No node is available for the requested time window after applying reservations."
                    )
                vm_request_repo.update_vm_request_provisioning(
                    session=session,
                    db_request=request,
                    vmid=request.vmid,
                    assigned_node=selection.node,
                    placement_strategy_used=selection.strategy,
                    commit=False,
                )
            reservation = selections[updated.id]

        action = (
            "approved"
            if review_data.status == VMRequestStatus.approved
            else "rejected"
        )
        details = f"Reviewed VM request {request_id}: {action}"
        if review_data.status == VMRequestStatus.approved:
            details += (
                ", reserved node "
                f"{reservation.node if reservation else updated.assigned_node} for the approved time window"
            )
        if review_data.review_comment:
            details += f". Comment: {review_data.review_comment}"

        audit_service.log_action(
            session=session,
            user_id=reviewer.id,
            vmid=db_request.vmid,
            action="vm_request_review",
            details=details,
            commit=False,
        )
        session.commit()

        logger.info(
            f"Admin {reviewer.email} {action} VM request {request_id}"
        )
    except BadRequestError:
        session.rollback()
        raise
    except ValueError as exc:
        session.rollback()
        raise BadRequestError(str(exc)) from exc
    except Exception:
        logger.exception(
            "Failed to process review for VM request %s", request_id
        )
        session.rollback()

        raise ProvisioningError(
            "Failed to process review; scheduled provisioning setup may have failed."
        )

    refreshed = vm_request_repo.get_vm_request_by_id(
        session=session, request_id=updated.id
    )
    return _to_public(refreshed)
