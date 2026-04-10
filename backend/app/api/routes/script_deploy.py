"""服務模板腳本部署 API

提供服務模板的無人值守部署功能：
- POST /deploy: 啟動部署任務（背景執行）
- GET /status/{task_id}: 查詢部署進度
"""

import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import AdminUser, SessionDep
from app.repositories import resource as resource_repo
from app.schemas.script_deploy import (
    ScriptDeployRequest,
    ScriptDeployResponse,
    ScriptDeployStatus,
)
from app.services.network import script_deploy_service
from app.services.user import audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/script-deploy", tags=["script-deploy"])


@router.post("/deploy", response_model=ScriptDeployResponse)
def deploy_service_template(
    request: ScriptDeployRequest,
    current_user: AdminUser,
) -> ScriptDeployResponse:
    """啟動服務模板的無人值守部署。

    從 GitHub community-scripts/ProxmoxVE 下載腳本，
    以無人值守方式在 Proxmox 節點上部署服務容器。
    """
    task_id = script_deploy_service.start_deployment(
        request_data=request.model_dump(),
        user_id=str(current_user.id),
    )

    return ScriptDeployResponse(
        task_id=task_id,
        message=f"部署任務已啟動：{request.template_slug} → {request.hostname}",
    )


@router.get("/status/{task_id}", response_model=ScriptDeployStatus)
def get_deploy_status(
    task_id: str,
    current_user: AdminUser,
) -> ScriptDeployStatus:
    """查詢部署任務的當前狀態。"""
    task = script_deploy_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="找不到該部署任務")

    return ScriptDeployStatus(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress,
        vmid=task.vmid,
        message=task.message,
        error=task.error,
        output=task.output or None,
    )


@router.post("/register/{task_id}")
def register_deployed_resource(
    task_id: str,
    session: SessionDep,
    current_user: AdminUser,
) -> dict:
    """部署成功後，將容器註冊到資料庫。

    前端在確認部署成功（status=completed）後呼叫此端點，
    將新建的容器資訊寫入資料庫以便追蹤管理。
    """
    task = script_deploy_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="找不到該部署任務")
    if task.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="無權操作此部署任務")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任務尚未完成或已失敗")
    if task.vmid is None:
        raise HTTPException(status_code=400, detail="無法取得 VMID")

    try:
        resource_repo.create_resource(
            session=session,
            vmid=task.vmid,
            user_id=current_user.id,
            environment_type=task.template_name or "服務模板",
            os_info=None,
            expiry_date=None,
            commit=False,
        )

        audit_service.log_action(
            session=session,
            user_id=current_user.id,
            vmid=task.vmid,
            action="script_deploy",
            details=f"透過腳本部署服務模板，VMID: {task.vmid}",
            commit=False,
        )
        session.commit()

        return {
            "message": f"容器 VMID {task.vmid} 已成功註冊",
            "vmid": task.vmid,
        }
    except Exception as e:
        session.rollback()
        logger.error("註冊部署資源失敗: %s", e)
        raise HTTPException(status_code=500, detail=f"註冊資源失敗: {e}")
