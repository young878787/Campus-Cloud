"""審計日誌查看 API"""

import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, ResourceInfoDep, SessionDep
from app.crud import audit_log as audit_log_crud
from app.models import AuditAction, AuditLogsPublic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("/", response_model=AuditLogsPublic)
def get_all_audit_logs(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    vmid: int | None = None,
    user_id: str | None = None,
    action: AuditAction | None = None,
):
    """
    查看所有審計日誌（管理員專用）

    支持按 VMID、用戶 ID、操作類型篩選
    """
    # 權限檢查：僅管理員
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view all audit logs",
        )

    try:
        import uuid

        # 轉換 user_id 字符串為 UUID
        user_uuid = None
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid user_id format")

        logs, count = audit_log_crud.get_audit_logs(
            session=session,
            skip=skip,
            limit=limit,
            vmid=vmid,
            user_id=user_uuid,
            action=action,
        )

        data = [audit_log_crud.to_audit_log_public(log) for log in logs]
        return AuditLogsPublic(data=data, count=count)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get all audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my", response_model=AuditLogsPublic)
def get_my_audit_logs(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
):
    """查看當前用戶的所有操作記錄"""
    try:
        logs, count = audit_log_crud.get_audit_logs_by_user(
            session=session, user_id=current_user.id, skip=skip, limit=limit
        )

        data = [audit_log_crud.to_audit_log_public(log) for log in logs]
        return AuditLogsPublic(data=data, count=count)

    except Exception as e:
        logger.error(f"Failed to get user audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 將資源操作記錄端點移到 resources 路由下
# 這樣可以利用 ResourceInfoDep 自動檢查所有權


@router.get("/resources/{vmid}", response_model=AuditLogsPublic)
def get_resource_audit_logs(
    vmid: int,
    session: SessionDep,
    current_user: CurrentUser,
    resource_info: ResourceInfoDep,
    skip: int = 0,
    limit: int = 100,
):
    """
    查看特定資源的操作記錄

    權限：資源所有者或管理員
    """
    try:
        logs, count = audit_log_crud.get_audit_logs_by_vmid(
            session=session, vmid=vmid, skip=skip, limit=limit
        )

        data = [audit_log_crud.to_audit_log_public(log) for log in logs]
        return AuditLogsPublic(data=data, count=count)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit logs for resource {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
