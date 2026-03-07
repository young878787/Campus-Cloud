import uuid

from sqlmodel import Session

from app.models import AuditAction, AuditLog
from app.schemas import AuditLogPublic, AuditLogsPublic
from app.repositories import audit_log as audit_repo


def log_action(
    *,
    session: Session,
    user_id: uuid.UUID,
    vmid: int | None = None,
    action: AuditAction | str,
    details: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    return audit_repo.create_audit_log(
        session=session,
        user_id=user_id,
        vmid=vmid,
        action=action,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def get_all(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    vmid: int | None = None,
    user_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
) -> AuditLogsPublic:
    logs, count = audit_repo.get_audit_logs(
        session=session, skip=skip, limit=limit,
        vmid=vmid, user_id=user_id, action=action,
    )
    return AuditLogsPublic(data=[_to_public(log) for log in logs], count=count)


def get_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> AuditLogsPublic:
    logs, count = audit_repo.get_audit_logs_by_user(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    return AuditLogsPublic(data=[_to_public(log) for log in logs], count=count)


def get_by_vmid(
    *, session: Session, vmid: int, skip: int = 0, limit: int = 100
) -> AuditLogsPublic:
    logs, count = audit_repo.get_audit_logs_by_vmid(
        session=session, vmid=vmid, skip=skip, limit=limit
    )
    return AuditLogsPublic(data=[_to_public(log) for log in logs], count=count)


def _to_public(log: AuditLog) -> AuditLogPublic:
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
