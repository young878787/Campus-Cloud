"""Resource deletion request service.

提供「將刪除請求加入佇列」、「取消佇列中的刪除」、「scheduler 處理 pending」三組能力。
實際刪除邏輯仍委派給 `resource_service.delete`，本 service 只負責生命週期管理與 audit。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.exceptions import AppError
from app.models import (
    DeletionRequest,
    DeletionRequestStatus,
    Resource,
    User,
)
from app.services.resource import resource_service

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def create_deletion_request(
    *,
    session: Session,
    user_id: uuid.UUID,
    vmid: int,
    resource_info: dict,
    purge: bool = True,
    force: bool = False,
) -> DeletionRequest:
    """建立一筆 pending DeletionRequest。

    若該 vmid 已有 pending/running 的請求，直接回傳該請求避免重複佇列。
    """
    existing = session.exec(
        select(DeletionRequest).where(
            DeletionRequest.vmid == vmid,
            DeletionRequest.status.in_(  # type: ignore[union-attr]
                [DeletionRequestStatus.pending, DeletionRequestStatus.running]
            ),
        )
    ).first()
    if existing is not None:
        return existing

    req = DeletionRequest(
        user_id=user_id,
        vmid=vmid,
        name=resource_info.get("name"),
        node=resource_info.get("node"),
        resource_type=resource_info.get("type"),
        purge=purge,
        force=force,
        status=DeletionRequestStatus.pending,
        created_at=_utc_now(),
    )
    session.add(req)
    session.commit()
    session.refresh(req)
    logger.info("Queued deletion request %s for vmid=%s", req.id, vmid)
    return req


def cancel_deletion_request(
    *,
    session: Session,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    is_admin: bool,
) -> DeletionRequest:
    req = session.get(DeletionRequest, request_id)
    if req is None:
        raise AppError(404, "Deletion request not found")
    if not is_admin and req.user_id != user_id:
        raise AppError(403, "Not allowed to cancel this deletion request")
    if req.status != DeletionRequestStatus.pending:
        raise AppError(
            409,
            f"Cannot cancel deletion request in status={req.status.value}",
        )
    req.status = DeletionRequestStatus.cancelled
    req.completed_at = _utc_now()
    session.add(req)
    session.commit()
    session.refresh(req)
    logger.info("Cancelled deletion request %s (vmid=%s)", req.id, req.vmid)
    return req


def list_for_user(
    *,
    session: Session,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[DeletionRequest], int]:
    rows = session.exec(
        select(DeletionRequest)
        .where(DeletionRequest.user_id == user_id)
        .order_by(DeletionRequest.created_at.desc())  # type: ignore[union-attr]
        .offset(skip)
        .limit(limit)
    ).all()
    total = len(
        session.exec(
            select(DeletionRequest.id).where(DeletionRequest.user_id == user_id)
        ).all()
    )
    return list(rows), total


def list_all(
    *,
    session: Session,
    status: DeletionRequestStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[DeletionRequest], int]:
    stmt = select(DeletionRequest)
    if status is not None:
        stmt = stmt.where(DeletionRequest.status == status)
    stmt = stmt.order_by(DeletionRequest.created_at.desc()).offset(skip).limit(limit)  # type: ignore[union-attr]
    rows = session.exec(stmt).all()

    count_stmt = select(DeletionRequest.id)
    if status is not None:
        count_stmt = count_stmt.where(DeletionRequest.status == status)
    total = len(session.exec(count_stmt).all())
    return list(rows), total


def list_active_for_vmids(
    *,
    session: Session,
    vmids: list[int],
) -> dict[int, DeletionRequest]:
    """回傳 vmid → 仍進行中（pending/running）的 DeletionRequest 的 mapping。"""
    if not vmids:
        return {}
    rows = session.exec(
        select(DeletionRequest).where(
            DeletionRequest.vmid.in_(vmids),  # type: ignore[union-attr]
            DeletionRequest.status.in_(  # type: ignore[union-attr]
                [DeletionRequestStatus.pending, DeletionRequestStatus.running]
            ),
        )
    ).all()
    return {r.vmid: r for r in rows}


# ──────────────────────────────────────────────────────────────────────────────
# Scheduler tick
# ──────────────────────────────────────────────────────────────────────────────


def process_pending_deletions(session: Session) -> None:
    """Scheduler tick：處理一輪 pending DeletionRequest。

    每個 tick 一次處理一筆，避免單一 tick 阻塞太久（刪除可能需要 30+ 秒）。
    """
    next_req = session.exec(
        select(DeletionRequest)
        .where(DeletionRequest.status == DeletionRequestStatus.pending)
        .order_by(DeletionRequest.created_at.asc())  # type: ignore[union-attr]
        .limit(1)
    ).first()

    if next_req is None:
        return

    # 標記 running
    next_req.status = DeletionRequestStatus.running
    next_req.started_at = _utc_now()
    session.add(next_req)
    session.commit()
    session.refresh(next_req)

    # 重新查 resource_info（可能已被別人改）
    resource = session.exec(
        select(Resource).where(Resource.vmid == next_req.vmid)
    ).first()
    if resource is None:
        next_req.status = DeletionRequestStatus.failed
        next_req.error_message = f"Resource vmid={next_req.vmid} not found at execute time"
        next_req.completed_at = _utc_now()
        session.add(next_req)
        session.commit()
        logger.warning(
            "Deletion request %s skipped: resource vmid=%s no longer exists",
            next_req.id, next_req.vmid,
        )
        return

    resource_info = {
        "vmid": resource.vmid,
        "node": resource.node,
        "type": resource.type,
        "name": resource.name,
        "status": resource.status,
    }

    try:
        resource_service.delete(
            session=session,
            vmid=next_req.vmid,
            resource_info=resource_info,
            user_id=next_req.user_id,
            purge=next_req.purge,
            force=next_req.force,
        )
        # resource_service.delete 已 commit 了 resource_repo.delete_resource 等。
        # 重新從 DB 撈本筆 deletion request 標記 completed（resource_service.delete 可能
        # 在中間 commit 過，物件已 detached）。
        fresh = session.get(DeletionRequest, next_req.id)
        if fresh is not None:
            fresh.status = DeletionRequestStatus.completed
            fresh.completed_at = _utc_now()
            session.add(fresh)
            session.commit()
        logger.info("Deletion request %s completed (vmid=%s)", next_req.id, next_req.vmid)
    except Exception as exc:
        logger.exception(
            "Deletion request %s failed (vmid=%s): %s",
            next_req.id, next_req.vmid, exc,
        )
        try:
            session.rollback()
        except Exception:
            pass
        fresh = session.get(DeletionRequest, next_req.id)
        if fresh is not None:
            fresh.status = DeletionRequestStatus.failed
            fresh.error_message = str(exc)[:2000]
            fresh.completed_at = _utc_now()
            session.add(fresh)
            session.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers for jobs/UI
# ──────────────────────────────────────────────────────────────────────────────


def to_public_with_user(
    *,
    session: Session,
    req: DeletionRequest,
) -> dict:
    user = session.get(User, req.user_id)
    return {
        "id": req.id,
        "user_id": req.user_id,
        "vmid": req.vmid,
        "name": req.name,
        "node": req.node,
        "resource_type": req.resource_type,
        "purge": req.purge,
        "force": req.force,
        "status": req.status,
        "error_message": req.error_message,
        "created_at": req.created_at,
        "started_at": req.started_at,
        "completed_at": req.completed_at,
        "user_email": user.email if user is not None else None,
        "user_full_name": user.full_name if user is not None else None,
    }
