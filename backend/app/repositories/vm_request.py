import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import selectinload
from sqlmodel import Session, func, select

from app.models import VMRequest, VMRequestStatus
from app.schemas import VMRequestCreate


def create_vm_request(
    *,
    session: Session,
    vm_request_in: VMRequestCreate,
    user_id: uuid.UUID,
    encrypted_password: str,
) -> VMRequest:
    """Create VM request. Password should be pre-encrypted by the service layer."""
    db_request = VMRequest(
        user_id=user_id,
        reason=vm_request_in.reason,
        resource_type=vm_request_in.resource_type,
        hostname=vm_request_in.hostname,
        cores=vm_request_in.cores,
        memory=vm_request_in.memory,
        password=encrypted_password,
        storage=vm_request_in.storage,
        environment_type="自訂規格",
        os_info=vm_request_in.os_info,
        expiry_date=vm_request_in.expiry_date,
        ostemplate=vm_request_in.ostemplate,
        rootfs_size=vm_request_in.rootfs_size,
        template_id=vm_request_in.template_id,
        disk_size=vm_request_in.disk_size,
        username=vm_request_in.username,
        status=VMRequestStatus.pending,
        created_at=datetime.now(timezone.utc),
    )
    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    return db_request


def get_vm_request_by_id(
    *, session: Session, request_id: uuid.UUID, for_update: bool = False
) -> VMRequest | None:
    statement = (
        select(VMRequest)
        .where(VMRequest.id == request_id)
        .options(selectinload(VMRequest.user))  # type: ignore[arg-type]
    )
    if for_update:
        statement = statement.with_for_update()
    return session.exec(statement).first()


def get_vm_requests_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> tuple[list[VMRequest], int]:
    count = session.exec(
        select(func.count()).select_from(VMRequest).where(VMRequest.user_id == user_id)
    ).one()
    statement = (
        select(VMRequest)
        .where(VMRequest.user_id == user_id)
        .options(selectinload(VMRequest.user))  # type: ignore[arg-type]
        .order_by(VMRequest.created_at.desc())  # type: ignore[union-attr]
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(statement).all()), count


def get_all_vm_requests(
    *,
    session: Session,
    status: VMRequestStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[VMRequest], int]:
    base = select(func.count()).select_from(VMRequest)
    if status:
        base = base.where(VMRequest.status == status)
    count = session.exec(base).one()

    statement = (
        select(VMRequest)
        .options(selectinload(VMRequest.user))  # type: ignore[arg-type]
        .order_by(VMRequest.created_at.desc())  # type: ignore[union-attr]
    )
    if status:
        statement = statement.where(VMRequest.status == status)
    return list(session.exec(statement.offset(skip).limit(limit)).all()), count


def update_vm_request_status(
    *,
    session: Session,
    db_request: VMRequest,
    status: VMRequestStatus,
    reviewer_id: uuid.UUID,
    review_comment: str | None = None,
    vmid: int | None = None,
) -> VMRequest:
    db_request.status = status
    db_request.reviewer_id = reviewer_id
    db_request.review_comment = review_comment
    db_request.reviewed_at = datetime.now(timezone.utc)
    if vmid is not None:
        db_request.vmid = vmid
    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    return db_request
