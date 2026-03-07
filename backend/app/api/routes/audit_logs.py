import uuid

from fastapi import APIRouter

from app.api.deps import AdminUser, CurrentUser, ResourceInfoDep, SessionDep
from app.exceptions import BadRequestError
from app.models import AuditAction
from app.schemas import AuditLogsPublic
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("/", response_model=AuditLogsPublic)
def get_all_audit_logs(
    session: SessionDep,
    current_user: AdminUser,
    skip: int = 0,
    limit: int = 100,
    vmid: int | None = None,
    user_id: str | None = None,
    action: AuditAction | None = None,
):
    user_uuid = None
    if user_id:
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise BadRequestError("Invalid user_id format")
    return audit_service.get_all(
        session=session,
        skip=skip,
        limit=limit,
        vmid=vmid,
        user_id=user_uuid,
        action=action,
    )


@router.get("/my", response_model=AuditLogsPublic)
def get_my_audit_logs(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
):
    return audit_service.get_by_user(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )


@router.get("/resources/{vmid}", response_model=AuditLogsPublic)
def get_resource_audit_logs(
    vmid: int,
    session: SessionDep,
    current_user: CurrentUser,
    resource_info: ResourceInfoDep,
    skip: int = 0,
    limit: int = 100,
):
    return audit_service.get_by_vmid(
        session=session, vmid=vmid, skip=skip, limit=limit
    )
