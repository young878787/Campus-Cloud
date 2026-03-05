"""規格調整申請 API - 申請與審核流程"""

import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, ResourceInfoDep, SessionDep
from app.core.proxmox import get_proxmox_api
from app.crud import audit_log as audit_log_crud
from app.crud import spec_change_request as spec_request_crud
from app.models import (
    SpecChangeRequestCreate,
    SpecChangeRequestPublic,
    SpecChangeRequestReview,
    SpecChangeRequestsPublic,
    SpecChangeRequestStatus,
    SpecChangeType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spec-change-requests", tags=["spec-change-requests"])


@router.post("/", response_model=SpecChangeRequestPublic)
def create_spec_change_request(
    request_in: SpecChangeRequestCreate,
    session: SessionDep,
    current_user: CurrentUser,
    resource_info: ResourceInfoDep = None,
):
    """提交規格調整申請（一般用戶）"""
    try:
        # 獲取資源信息以驗證所有權
        proxmox = get_proxmox_api()
        vmid = request_in.vmid

        # 使用 ResourceInfoDep 手動檢查所有權（通過路徑參數自動檢查不適用於 POST body）
        from app.api.deps.proxmox import check_resource_ownership

        resource_info_dict = check_resource_ownership(
            session=session, current_user=current_user, vmid=vmid
        )
        node = resource_info_dict["node"]
        resource_type = resource_info_dict["type"]

        # 獲取當前規格
        if resource_type == "qemu":
            config = proxmox.nodes(node).qemu(vmid).config.get()
        else:
            config = proxmox.nodes(node).lxc(vmid).config.get()

        current_cpu = config.get("cores") or config.get("cpus")
        current_memory = config.get("memory")
        # 磁碟大小較複雜，需要解析
        current_disk = None
        if resource_type == "qemu":
            # QEMU: scsi0 格式如 "local-lvm:vm-103-disk-0,size=32G"
            scsi0 = config.get("scsi0", "")
            if "size=" in scsi0:
                size_str = scsi0.split("size=")[1].split(",")[0].split(")")[0]
                if size_str.endswith("G"):
                    current_disk = int(size_str[:-1])
        else:
            # LXC: rootfs 格式如 "local-lvm:vm-103-disk-0,size=8G"
            rootfs = config.get("rootfs", "")
            if "size=" in rootfs:
                size_str = rootfs.split("size=")[1].split(",")[0]
                if size_str.endswith("G"):
                    current_disk = int(size_str[:-1])

        # 驗證請求的規格變更
        if request_in.change_type == SpecChangeType.cpu:
            if request_in.requested_cpu is None:
                raise HTTPException(
                    status_code=400, detail="requested_cpu is required for CPU change"
                )
        elif request_in.change_type == SpecChangeType.memory:
            if request_in.requested_memory is None:
                raise HTTPException(
                    status_code=400,
                    detail="requested_memory is required for memory change",
                )
        elif request_in.change_type == SpecChangeType.disk:
            if request_in.requested_disk is None:
                raise HTTPException(
                    status_code=400, detail="requested_disk is required for disk change"
                )
            # 磁碟只能增加不能減少
            if current_disk and request_in.requested_disk <= current_disk:
                raise HTTPException(
                    status_code=400,
                    detail=f"Disk size can only be increased. Current: {current_disk}GB",
                )
        elif request_in.change_type == SpecChangeType.combined:
            if not any(
                [
                    request_in.requested_cpu,
                    request_in.requested_memory,
                    request_in.requested_disk,
                ]
            ):
                raise HTTPException(
                    status_code=400,
                    detail="At least one specification must be requested for combined change",
                )

        # 創建申請
        db_request = spec_request_crud.create_spec_change_request(
            session=session,
            user_id=current_user.id,
            vmid=vmid,
            change_type=request_in.change_type,
            reason=request_in.reason,
            current_cpu=current_cpu,
            current_memory=current_memory,
            current_disk=current_disk,
            requested_cpu=request_in.requested_cpu,
            requested_memory=request_in.requested_memory,
            requested_disk=request_in.requested_disk,
        )

        # 記錄審計日誌
        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=vmid,
            action="spec_change_request",
            details=f"Requested {request_in.change_type.value} change: CPU={request_in.requested_cpu}, Memory={request_in.requested_memory}MB, Disk={request_in.requested_disk}GB. Reason: {request_in.reason}",
        )

        logger.info(
            f"User {current_user.email} created spec change request for VMID {vmid}"
        )
        return spec_request_crud.to_spec_change_request_public(db_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create spec change request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my", response_model=SpecChangeRequestsPublic)
def get_my_spec_change_requests(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
):
    """查看當前用戶的所有規格調整申請"""
    try:
        requests, count = spec_request_crud.get_spec_change_requests_by_user(
            session=session, user_id=current_user.id, skip=skip, limit=limit
        )

        data = [spec_request_crud.to_spec_change_request_public(r) for r in requests]
        return SpecChangeRequestsPublic(data=data, count=count)

    except Exception as e:
        logger.error(f"Failed to get user spec change requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=SpecChangeRequestsPublic)
def get_all_spec_change_requests(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    status: SpecChangeRequestStatus | None = None,
    vmid: int | None = None,
):
    """查看所有規格調整申請（管理員專用）"""
    # 權限檢查：僅管理員
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view all spec change requests",
        )

    try:
        requests, count = spec_request_crud.get_all_spec_change_requests(
            session=session, skip=skip, limit=limit, status=status, vmid=vmid
        )

        data = [spec_request_crud.to_spec_change_request_public(r) for r in requests]
        return SpecChangeRequestsPublic(data=data, count=count)

    except Exception as e:
        logger.error(f"Failed to get all spec change requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{request_id}/review", response_model=SpecChangeRequestPublic)
def review_spec_change_request(
    request_id: str,
    review: SpecChangeRequestReview,
    session: SessionDep,
    current_user: CurrentUser,
):
    """審核規格調整申請（管理員專用）"""
    # 權限檢查：僅管理員
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can review spec change requests",
        )

    try:
        # 獲取申請
        db_request = spec_request_crud.get_spec_change_request_by_id(
            session=session, request_id=request_id
        )
        if not db_request:
            raise HTTPException(status_code=404, detail="Request not found")

        # 檢查狀態
        if db_request.status != SpecChangeRequestStatus.pending:
            raise HTTPException(
                status_code=400,
                detail=f"Request already {db_request.status.value}",
            )

        # 更新審核狀態
        db_request = spec_request_crud.update_spec_change_request_status(
            session=session,
            request_id=request_id,
            status=review.status,
            reviewer_id=current_user.id,
            review_comment=review.review_comment,
        )

        # 如果批准，則應用規格調整
        if review.status == SpecChangeRequestStatus.approved:
            try:
                proxmox = get_proxmox_api()
                from app.api.deps.proxmox import check_resource_ownership

                # 驗證資源仍然存在
                resource_info = check_resource_ownership(
                    session=session,
                    current_user=current_user,
                    vmid=db_request.vmid,
                )
                node = resource_info["node"]
                resource_type = resource_info["type"]

                # 準備配置更新
                config_params = {}
                changes = []

                if db_request.requested_cpu is not None:
                    config_params["cores"] = db_request.requested_cpu
                    changes.append(
                        f"CPU: {db_request.current_cpu} -> {db_request.requested_cpu} cores"
                    )

                if db_request.requested_memory is not None:
                    config_params["memory"] = db_request.requested_memory
                    changes.append(
                        f"Memory: {db_request.current_memory} -> {db_request.requested_memory}MB"
                    )

                # 應用 CPU 和記憶體變更
                if config_params:
                    if resource_type == "qemu":
                        proxmox.nodes(node).qemu(db_request.vmid).config.put(
                            **config_params
                        )
                    else:
                        proxmox.nodes(node).lxc(db_request.vmid).config.put(
                            **config_params
                        )

                # 應用磁碟變更
                if db_request.requested_disk is not None:
                    disk_increase = (
                        db_request.requested_disk - (db_request.current_disk or 0)
                    )
                    size_param = f"+{disk_increase}G"

                    if resource_type == "qemu":
                        proxmox.nodes(node).qemu(db_request.vmid).resize.put(
                            disk="scsi0", size=size_param
                        )
                    else:
                        proxmox.nodes(node).lxc(db_request.vmid).resize.put(
                            disk="rootfs", size=size_param
                        )
                    changes.append(
                        f"Disk: {db_request.current_disk} -> {db_request.requested_disk}GB"
                    )

                # 標記為已應用
                spec_request_crud.mark_spec_change_applied(
                    session=session, request_id=request_id
                )

                # 記錄審計日誌
                audit_log_crud.create_audit_log(
                    session=session,
                    user_id=current_user.id,
                    vmid=db_request.vmid,
                    action="spec_change_apply",
                    details=f"Applied approved spec changes: {', '.join(changes)}",
                )

                logger.info(
                    f"Admin {current_user.email} approved and applied spec change request {request_id}"
                )

            except Exception as e:
                logger.error(f"Failed to apply spec changes: {e}")
                # 即使應用失敗，審核狀態已更新
                raise HTTPException(
                    status_code=500,
                    detail=f"Request approved but failed to apply changes: {str(e)}",
                )
        else:
            # 拒絕申請
            audit_log_crud.create_audit_log(
                session=session,
                user_id=current_user.id,
                vmid=db_request.vmid,
                action="spec_change_request",
                details=f"Rejected spec change request {request_id}: {review.review_comment or 'No comment'}",
            )
            logger.info(
                f"Admin {current_user.email} rejected spec change request {request_id}"
            )

        return spec_request_crud.to_spec_change_request_public(db_request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to review spec change request: {e}")
        raise HTTPException(status_code=500, detail=str(e))
