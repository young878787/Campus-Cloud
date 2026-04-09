"""群組批量建立資源 API"""

import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import AdminUser, SessionDep
from app.exceptions import BadRequestError, NotFoundError
from app.repositories import batch_provision as bp_repo
from app.repositories import group as group_repo
from app.services import batch_provision_service
from app.models import User
from sqlmodel import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-provision", tags=["batch-provision"])


# ─── Request / Response Schemas ───────────────────────────────────────────────


class BatchProvisionRequest(BaseModel):
    """批量建立參數（與 ResourceCreatePage 表單對應）"""

    resource_type: str = Field(..., pattern="^(lxc|qemu)$")
    hostname_prefix: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)
    cores: int = Field(2, ge=1, le=32)
    memory: int = Field(2048, ge=128, le=65536)
    environment_type: str = Field(default="批量建立")
    os_info: str | None = None
    expiry_date: date | None = None

    # LXC 欄位
    ostemplate: str | None = None
    rootfs_size: int | None = Field(default=8, ge=1, le=1000)

    # VM 欄位
    template_id: int | None = None
    username: str | None = None
    disk_size: int | None = Field(default=20, ge=10, le=1000)


class BatchProvisionTaskPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None
    user_name: str | None
    member_index: int
    vmid: int | None
    status: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class BatchProvisionJobPublic(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    resource_type: str
    hostname_prefix: str
    status: str
    total: int
    done: int
    failed_count: int
    created_at: datetime
    finished_at: datetime | None
    tasks: list[BatchProvisionTaskPublic]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _validate_request(body: BatchProvisionRequest) -> None:
    if body.resource_type == "lxc":
        if not body.ostemplate:
            raise BadRequestError("LXC 建立需要指定 ostemplate")
    else:
        if not body.template_id:
            raise BadRequestError("VM 建立需要指定 template_id")
        if not body.username:
            raise BadRequestError("VM 建立需要指定 username")


def _build_job_public(session, job) -> BatchProvisionJobPublic:
    tasks = bp_repo.get_job_tasks(session=session, job_id=job.id)

    # 一次查出所有涉及的 user
    user_ids = [t.user_id for t in tasks]
    users: dict[uuid.UUID, User] = {}
    if user_ids:
        results = session.exec(
            select(User).where(User.id.in_(user_ids))
        ).all()
        users = {u.id: u for u in results}

    task_publics = [
        BatchProvisionTaskPublic(
            id=t.id,
            user_id=t.user_id,
            user_email=users[t.user_id].email if t.user_id in users else None,
            user_name=users[t.user_id].full_name if t.user_id in users else None,
            member_index=t.member_index,
            vmid=t.vmid,
            status=t.status,
            error=t.error,
            started_at=t.started_at,
            finished_at=t.finished_at,
        )
        for t in tasks
    ]

    return BatchProvisionJobPublic(
        id=job.id,
        group_id=job.group_id,
        resource_type=job.resource_type,
        hostname_prefix=job.hostname_prefix,
        status=job.status,
        total=job.total,
        done=job.done,
        failed_count=job.failed_count,
        created_at=job.created_at,
        finished_at=job.finished_at,
        tasks=task_publics,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/{group_id}", response_model=BatchProvisionJobPublic)
def start_batch_provision(
    group_id: uuid.UUID,
    body: BatchProvisionRequest,
    session: SessionDep,
    current_user: AdminUser,
) -> BatchProvisionJobPublic:
    """
    為群組所有成員批量建立資源（LXC 或 VM）。
    建立後立即回傳，實際建立在背景逐一排隊執行。
    """
    _validate_request(body)

    db_group = group_repo.get_group_by_id(session=session, group_id=group_id)
    if not db_group:
        raise NotFoundError("群組不存在")

    # 序列化參數（排除 resource_type 和 hostname_prefix，service 自己組）
    params = body.model_dump(
        exclude={"resource_type", "hostname_prefix"},
        exclude_none=False,
    )
    # 將 date 轉為 ISO string，方便 JSON 序列化
    if params.get("expiry_date"):
        params["expiry_date"] = params["expiry_date"].isoformat()

    job_id = batch_provision_service.start_batch_job(
        session=session,
        group_id=group_id,
        initiated_by_id=current_user.id,
        resource_type=body.resource_type,
        hostname_prefix=body.hostname_prefix,
        params=params,
    )

    job = bp_repo.get_job(session=session, job_id=job_id)
    return _build_job_public(session, job)


@router.get("/{job_id}/status", response_model=BatchProvisionJobPublic)
def get_batch_status(
    job_id: uuid.UUID,
    session: SessionDep,
    current_user: AdminUser,
) -> BatchProvisionJobPublic:
    """輪詢批量建立工作的進度。"""
    job = bp_repo.get_job(session=session, job_id=job_id)
    if not job:
        raise NotFoundError("批量工作不存在")
    return _build_job_public(session, job)


@router.get("/group/{group_id}", response_model=list[BatchProvisionJobPublic])
def list_group_jobs(
    group_id: uuid.UUID,
    session: SessionDep,
    current_user: AdminUser,
) -> list[BatchProvisionJobPublic]:
    """列出某群組的所有批量建立紀錄（最新在前）。"""
    jobs = bp_repo.list_jobs_by_group(session=session, group_id=group_id)
    return [_build_job_public(session, j) for j in jobs]
