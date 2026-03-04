"""規格調整申請 CRUD 操作"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import selectinload
from sqlmodel import Session, func, select

from app.models import (
    SpecChangeRequest,
    SpecChangeRequestPublic,
    SpecChangeRequestStatus,
)


def create_spec_change_request(
    *,
    session: Session,
    user_id: uuid.UUID,
    vmid: int,
    change_type: str,
    reason: str,
    current_cpu: int | None = None,
    current_memory: int | None = None,
    current_disk: int | None = None,
    requested_cpu: int | None = None,
    requested_memory: int | None = None,
    requested_disk: int | None = None,
) -> SpecChangeRequest:
    """創建規格調整申請"""
    db_request = SpecChangeRequest(
        vmid=vmid,
        user_id=user_id,
        change_type=change_type,
        reason=reason,
        current_cpu=current_cpu,
        current_memory=current_memory,
        current_disk=current_disk,
        requested_cpu=requested_cpu,
        requested_memory=requested_memory,
        requested_disk=requested_disk,
        status=SpecChangeRequestStatus.pending,
        created_at=datetime.now(timezone.utc),
    )
    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    return db_request


def get_spec_change_request_by_id(
    *, session: Session, request_id: uuid.UUID, for_update: bool = False
) -> SpecChangeRequest | None:
    """根據 ID 獲取規格調整申請"""
    statement = (
        select(SpecChangeRequest)
        .options(selectinload(SpecChangeRequest.user))
        .options(selectinload(SpecChangeRequest.reviewer))
        .where(SpecChangeRequest.id == request_id)
    )
    if for_update:
        statement = statement.with_for_update()
    return session.exec(statement).first()


def get_spec_change_requests_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> tuple[list[SpecChangeRequest], int]:
    """獲取特定用戶的規格調整申請"""
    # 計算總數
    count_statement = select(func.count()).select_from(SpecChangeRequest).where(
        SpecChangeRequest.user_id == user_id
    )
    count = session.exec(count_statement).one()

    # 獲取申請列表
    statement = (
        select(SpecChangeRequest)
        .options(selectinload(SpecChangeRequest.user))
        .options(selectinload(SpecChangeRequest.reviewer))
        .where(SpecChangeRequest.user_id == user_id)
        .order_by(SpecChangeRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    requests = list(session.exec(statement).all())
    return requests, count


def get_all_spec_change_requests(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    status: SpecChangeRequestStatus | str | None = None,
    vmid: int | None = None,
) -> tuple[list[SpecChangeRequest], int]:
    """獲取所有規格調整申請（管理員，支持篩選和分頁）"""
    # 構建查詢條件
    filters = []
    if status is not None:
        if isinstance(status, str):
            status = SpecChangeRequestStatus(status)
        filters.append(SpecChangeRequest.status == status)
    if vmid is not None:
        filters.append(SpecChangeRequest.vmid == vmid)

    # 計算總數
    count_statement = select(func.count()).select_from(SpecChangeRequest)
    if filters:
        for f in filters:
            count_statement = count_statement.where(f)
    count = session.exec(count_statement).one()

    # 獲取申請列表
    statement = (
        select(SpecChangeRequest)
        .options(selectinload(SpecChangeRequest.user))
        .options(selectinload(SpecChangeRequest.reviewer))
        .order_by(SpecChangeRequest.created_at.desc())
    )
    if filters:
        for f in filters:
            statement = statement.where(f)
    statement = statement.offset(skip).limit(limit)

    requests = list(session.exec(statement).all())
    return requests, count


def update_spec_change_request_status(
    *,
    session: Session,
    request_id: uuid.UUID,
    status: SpecChangeRequestStatus | str,
    reviewer_id: uuid.UUID,
    review_comment: str | None = None,
) -> SpecChangeRequest:
    """更新規格調整申請狀態"""
    if isinstance(status, str):
        status = SpecChangeRequestStatus(status)

    db_request = get_spec_change_request_by_id(
        session=session, request_id=request_id, for_update=True
    )
    if not db_request:
        raise ValueError(f"Spec change request {request_id} not found")

    db_request.status = status
    db_request.reviewer_id = reviewer_id
    db_request.review_comment = review_comment
    db_request.reviewed_at = datetime.now(timezone.utc)

    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    return db_request


def mark_spec_change_applied(
    *, session: Session, request_id: uuid.UUID
) -> SpecChangeRequest:
    """標記規格調整已應用"""
    db_request = get_spec_change_request_by_id(
        session=session, request_id=request_id, for_update=True
    )
    if not db_request:
        raise ValueError(f"Spec change request {request_id} not found")

    db_request.applied_at = datetime.now(timezone.utc)
    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    return db_request


def to_spec_change_request_public(
    request: SpecChangeRequest,
) -> SpecChangeRequestPublic:
    """轉換為公開模型"""
    return SpecChangeRequestPublic(
        id=request.id,
        vmid=request.vmid,
        user_id=request.user_id,
        user_email=request.user.email if request.user else None,
        user_full_name=request.user.full_name if request.user else None,
        change_type=request.change_type,
        reason=request.reason,
        current_cpu=request.current_cpu,
        current_memory=request.current_memory,
        current_disk=request.current_disk,
        requested_cpu=request.requested_cpu,
        requested_memory=request.requested_memory,
        requested_disk=request.requested_disk,
        status=request.status,
        reviewer_id=request.reviewer_id,
        review_comment=request.review_comment,
        reviewed_at=request.reviewed_at,
        applied_at=request.applied_at,
        created_at=request.created_at,
    )


__all__ = [
    "create_spec_change_request",
    "get_spec_change_request_by_id",
    "get_spec_change_requests_by_user",
    "get_all_spec_change_requests",
    "update_spec_change_request_status",
    "mark_spec_change_applied",
    "to_spec_change_request_public",
]
