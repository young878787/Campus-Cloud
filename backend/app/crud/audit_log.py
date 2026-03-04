"""審計日誌 CRUD 操作"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import selectinload
from sqlmodel import Session, func, select

from app.models import AuditAction, AuditLog, AuditLogPublic


def create_audit_log(
    *,
    session: Session,
    user_id: uuid.UUID,
    vmid: int | None,
    action: AuditAction | str,
    details: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """創建審計日誌"""
    if isinstance(action, str):
        action = AuditAction(action)

    db_log = AuditLog(
        user_id=user_id,
        vmid=vmid,
        action=action,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=datetime.now(timezone.utc),
    )
    session.add(db_log)
    session.commit()
    session.refresh(db_log)
    return db_log


def get_audit_logs(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    vmid: int | None = None,
    user_id: uuid.UUID | None = None,
    action: AuditAction | str | None = None,
) -> tuple[list[AuditLog], int]:
    """獲取所有審計日誌（管理員，支持篩選和分頁）"""
    # 構建查詢條件
    filters = []
    if vmid is not None:
        filters.append(AuditLog.vmid == vmid)
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if action is not None:
        if isinstance(action, str):
            action = AuditAction(action)
        filters.append(AuditLog.action == action)

    # 計算總數
    count_statement = select(func.count()).select_from(AuditLog)
    if filters:
        for f in filters:
            count_statement = count_statement.where(f)
    count = session.exec(count_statement).one()

    # 獲取日誌列表
    statement = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
    )
    if filters:
        for f in filters:
            statement = statement.where(f)
    statement = statement.offset(skip).limit(limit)

    logs = list(session.exec(statement).all())
    return logs, count


def get_audit_logs_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> tuple[list[AuditLog], int]:
    """獲取特定用戶的審計日誌"""
    return get_audit_logs(session=session, user_id=user_id, skip=skip, limit=limit)


def get_audit_logs_by_vmid(
    *, session: Session, vmid: int, skip: int = 0, limit: int = 100
) -> tuple[list[AuditLog], int]:
    """獲取特定資源的審計日誌"""
    return get_audit_logs(session=session, vmid=vmid, skip=skip, limit=limit)


def to_audit_log_public(log: AuditLog) -> AuditLogPublic:
    """轉換為公開模型"""
    return AuditLogPublic(
        id=log.id,
        user_id=log.user_id,
        user_email=log.user.email if log.user else None,
        user_full_name=log.user.full_name if log.user else None,
        vmid=log.vmid,
        action=log.action,
        details=log.details,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        created_at=log.created_at,
    )


__all__ = [
    "create_audit_log",
    "get_audit_logs",
    "get_audit_logs_by_user",
    "get_audit_logs_by_vmid",
    "to_audit_log_public",
]
