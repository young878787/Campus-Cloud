"""資源詳細信息 API - 快照、監控、規格調整等"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, ResourceInfoDep, SessionDep
from app.core.proxmox import basic_blocking_task_status, get_proxmox_api
from app.crud import audit_log as audit_log_crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["resource-details"])


# ===== 監控數據 Schemas =====


class CurrentStatsResponse(BaseModel):
    """當前實時狀態"""

    cpu: float | None = Field(None, description="CPU 使用率 (0-1)")
    maxcpu: int | None = Field(None, description="CPU 核心數")
    mem: int | None = Field(None, description="當前記憶體使用 (bytes)")
    maxmem: int | None = Field(None, description="最大記憶體 (bytes)")
    disk: int | None = Field(None, description="當前磁碟使用 (bytes)")
    maxdisk: int | None = Field(None, description="最大磁碟 (bytes)")
    netin: int | None = Field(None, description="網絡輸入 (bytes)")
    netout: int | None = Field(None, description="網絡輸出 (bytes)")
    uptime: int | None = Field(None, description="運行時間 (seconds)")
    status: str = Field(..., description="狀態 (running, stopped, etc.)")


class RRDDataPoint(BaseModel):
    """RRD 數據點"""

    time: int = Field(..., description="時間戳")
    cpu: float | None = None
    maxcpu: int | None = None
    mem: float | None = None
    maxmem: float | None = None
    disk: float | None = None
    maxdisk: float | None = None
    netin: float | None = None
    netout: float | None = None


class RRDDataResponse(BaseModel):
    """RRD 歷史數據響應"""

    timeframe: str = Field(..., description="時間範圍")
    data: list[RRDDataPoint] = Field(..., description="數據點列表")


# ===== 快照 Schemas =====


class SnapshotInfo(BaseModel):
    """快照信息"""

    name: str = Field(..., description="快照名稱")
    description: str | None = Field(None, description="快照描述")
    snaptime: int | None = Field(None, description="創建時間戳")
    vmstate: int | None = Field(None, description="是否包含 VM 狀態 (0/1)")


class SnapshotCreateRequest(BaseModel):
    """創建快照請求"""

    snapname: str = Field(..., min_length=1, max_length=40, description="快照名稱")
    description: str | None = Field(None, max_length=255, description="快照描述")
    vmstate: bool = Field(False, description="是否包含 RAM 狀態 (僅 VM)")


class SnapshotResponse(BaseModel):
    """快照操作響應"""

    message: str
    task_id: str | None = None


# ===== 規格調整 Schemas =====


class DirectSpecUpdateRequest(BaseModel):
    """管理員直接調整規格"""

    cores: int | None = Field(None, ge=1, le=32, description="CPU 核心數")
    memory: int | None = Field(None, ge=512, le=65536, description="記憶體 (MB)")
    disk_size: str | None = Field(
        None, description='磁碟大小增量 (例如 "+10G"，僅能增加)'
    )


# ===== 監控 API =====


@router.get("/{vmid}/current-stats", response_model=CurrentStatsResponse)
def get_current_stats(vmid: int, resource_info: ResourceInfoDep):
    """獲取資源當前實時狀態"""
    try:
        proxmox = get_proxmox_api()
        node = resource_info["node"]
        resource_type = resource_info["type"]

        if resource_type == "qemu":
            current_status = proxmox.nodes(node).qemu(vmid).status.current.get()
        else:
            current_status = proxmox.nodes(node).lxc(vmid).status.current.get()

        return CurrentStatsResponse(
            cpu=current_status.get("cpu"),
            maxcpu=current_status.get("cpus") or current_status.get("maxcpu"),
            mem=current_status.get("mem"),
            maxmem=current_status.get("maxmem"),
            disk=current_status.get("disk"),
            maxdisk=current_status.get("maxdisk"),
            netin=current_status.get("netin"),
            netout=current_status.get("netout"),
            uptime=current_status.get("uptime"),
            status=current_status.get("status", "unknown"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get current stats for {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vmid}/stats", response_model=RRDDataResponse)
def get_rrd_stats(
    vmid: int,
    resource_info: ResourceInfoDep,
    timeframe: str = "hour",
):
    """
    獲取資源歷史統計數據 (RRD)

    timeframe: hour, day, week, month, year
    """
    valid_timeframes = ["hour", "day", "week", "month", "year"]
    if timeframe not in valid_timeframes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe. Must be one of: {valid_timeframes}",
        )

    try:
        proxmox = get_proxmox_api()
        node = resource_info["node"]
        resource_type = resource_info["type"]

        if resource_type == "qemu":
            rrd_data = proxmox.nodes(node).qemu(vmid).rrddata.get(timeframe=timeframe)
        else:
            rrd_data = proxmox.nodes(node).lxc(vmid).rrddata.get(timeframe=timeframe)

        data_points = [
            RRDDataPoint(
                time=int(point.get("time", 0)),
                cpu=point.get("cpu"),
                maxcpu=point.get("maxcpu"),
                mem=point.get("mem"),
                maxmem=point.get("maxmem"),
                disk=point.get("disk"),
                maxdisk=point.get("maxdisk"),
                netin=point.get("netin"),
                netout=point.get("netout"),
            )
            for point in rrd_data
        ]

        return RRDDataResponse(timeframe=timeframe, data=data_points)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get RRD stats for {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 快照管理 API =====


@router.get("/{vmid}/snapshots", response_model=list[SnapshotInfo])
def list_snapshots(vmid: int, resource_info: ResourceInfoDep):
    """列出所有快照"""
    try:
        proxmox = get_proxmox_api()
        node = resource_info["node"]
        resource_type = resource_info["type"]

        if resource_type == "qemu":
            snapshots = proxmox.nodes(node).qemu(vmid).snapshot.get()
        else:
            snapshots = proxmox.nodes(node).lxc(vmid).snapshot.get()

        # 過濾掉 "current" 項（不是真正的快照）
        result = [
            SnapshotInfo(
                name=snap.get("name", ""),
                description=snap.get("description"),
                snaptime=snap.get("snaptime"),
                vmstate=snap.get("vmstate"),
            )
            for snap in snapshots
            if snap.get("name") != "current"
        ]

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list snapshots for {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{vmid}/snapshots", response_model=SnapshotResponse)
def create_snapshot(
    vmid: int,
    request: SnapshotCreateRequest,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    """創建快照"""
    try:
        proxmox = get_proxmox_api()
        node = resource_info["node"]
        resource_type = resource_info["type"]

        params = {
            "snapname": request.snapname,
        }
        if request.description:
            params["description"] = request.description
        if resource_type == "qemu" and request.vmstate:
            params["vmstate"] = 1

        if resource_type == "qemu":
            task = proxmox.nodes(node).qemu(vmid).snapshot.post(**params)
        else:
            task = proxmox.nodes(node).lxc(vmid).snapshot.post(**params)

        # 等待任務完成
        basic_blocking_task_status(node, task)

        # 記錄審計日誌
        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=vmid,
            action="snapshot_create",
            details=f"Created snapshot '{request.snapname}': {request.description or 'No description'}",
        )

        logger.info(f"Snapshot '{request.snapname}' created for {vmid}")
        return SnapshotResponse(
            message=f"Snapshot '{request.snapname}' created successfully",
            task_id=task,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create snapshot for {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{vmid}/snapshots/{snapname}", response_model=SnapshotResponse)
def delete_snapshot(
    vmid: int,
    snapname: str,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    """刪除快照"""
    try:
        proxmox = get_proxmox_api()
        node = resource_info["node"]
        resource_type = resource_info["type"]

        if resource_type == "qemu":
            task = proxmox.nodes(node).qemu(vmid).snapshot(snapname).delete()
        else:
            task = proxmox.nodes(node).lxc(vmid).snapshot(snapname).delete()

        # 等待任務完成
        basic_blocking_task_status(node, task)

        # 記錄審計日誌
        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=vmid,
            action="snapshot_delete",
            details=f"Deleted snapshot '{snapname}'",
        )

        logger.info(f"Snapshot '{snapname}' deleted for {vmid}")
        return SnapshotResponse(
            message=f"Snapshot '{snapname}' deleted successfully",
            task_id=task,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete snapshot '{snapname}' for {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{vmid}/snapshots/{snapname}/rollback", response_model=SnapshotResponse
)
def rollback_snapshot(
    vmid: int,
    snapname: str,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    """回滾到指定快照"""
    try:
        proxmox = get_proxmox_api()
        node = resource_info["node"]
        resource_type = resource_info["type"]

        if resource_type == "qemu":
            task = proxmox.nodes(node).qemu(vmid).snapshot(snapname).rollback.post()
        else:
            task = proxmox.nodes(node).lxc(vmid).snapshot(snapname).rollback.post()

        # 等待任務完成
        basic_blocking_task_status(node, task)

        # 記錄審計日誌
        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=vmid,
            action="snapshot_rollback",
            details=f"Rolled back to snapshot '{snapname}'",
        )

        logger.info(f"Rolled back to snapshot '{snapname}' for {vmid}")
        return SnapshotResponse(
            message=f"Rolled back to snapshot '{snapname}' successfully",
            task_id=task,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback snapshot '{snapname}' for {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 規格調整 API (管理員專用) =====


@router.put("/{vmid}/spec/direct")
def direct_update_spec(
    vmid: int,
    request: DirectSpecUpdateRequest,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    """管理員直接調整資源規格（無需審核）"""
    # 權限檢查：僅管理員
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can directly update resource specifications",
        )

    try:
        proxmox = get_proxmox_api()
        node = resource_info["node"]
        resource_type = resource_info["type"]

        changes = []
        config_params = {}

        # 準備配置更新參數
        if request.cores is not None:
            config_params["cores"] = request.cores
            changes.append(f"CPU: {request.cores} cores")

        if request.memory is not None:
            config_params["memory"] = request.memory
            changes.append(f"Memory: {request.memory}MB")

        if not config_params and not request.disk_size:
            raise HTTPException(
                status_code=400,
                detail="At least one specification must be provided",
            )

        # 更新 CPU 和記憶體
        if config_params:
            if resource_type == "qemu":
                proxmox.nodes(node).qemu(vmid).config.put(**config_params)
            else:
                proxmox.nodes(node).lxc(vmid).config.put(**config_params)

        # 更新磁碟大小（僅增加）
        if request.disk_size:
            if resource_type == "qemu":
                # QEMU VM 使用 resize API
                proxmox.nodes(node).qemu(vmid).resize.put(
                    disk="scsi0", size=request.disk_size
                )
            else:
                # LXC 使用 config API 的 rootfs 參數
                proxmox.nodes(node).lxc(vmid).resize.put(
                    disk="rootfs", size=request.disk_size
                )
            changes.append(f"Disk: {request.disk_size}")

        # 記錄審計日誌
        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=vmid,
            action="spec_change_apply",
            details=f"Admin directly updated specs: {', '.join(changes)}",
        )

        logger.info(f"Admin {current_user.email} updated specs for {vmid}: {changes}")
        return {
            "message": "Resource specifications updated successfully",
            "changes": changes,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update specs for {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
