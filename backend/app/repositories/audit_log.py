import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import selectinload
from sqlmodel import Session, func, select

from app.models import AuditAction, AuditLog


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
    filters = []
    if vmid is not None:
        filters.append(AuditLog.vmid == vmid)
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if action is not None:
        if isinstance(action, str):
            action = AuditAction(action)
        filters.append(AuditLog.action == action)

    count_statement = select(func.count()).select_from(AuditLog)
    for f in filters:
        count_statement = count_statement.where(f)
    count = session.exec(count_statement).one()

    statement = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
    )
    for f in filters:
        statement = statement.where(f)
    statement = statement.offset(skip).limit(limit)
    return list(session.exec(statement).all()), count


def get_audit_logs_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> tuple[list[AuditLog], int]:
    return get_audit_logs(session=session, user_id=user_id, skip=skip, limit=limit)


def get_audit_logs_by_vmid(
    *, session: Session, vmid: int, skip: int = 0, limit: int = 100
) -> tuple[list[AuditLog], int]:
    return get_audit_logs(session=session, vmid=vmid, skip=skip, limit=limit)
