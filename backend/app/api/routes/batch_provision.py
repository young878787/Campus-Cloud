"""Batch provisioning APIs for group-owned VM/LXC creation jobs."""

import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import InstructorUser, SessionDep
from app.core.authorizers import require_group_access
from app.exceptions import BadRequestError, NotFoundError
from app.models import User
from app.repositories import batch_provision as bp_repo
from app.repositories import group as group_repo
from app.services.vm import batch_provision_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-provision", tags=["batch-provision"])


class BatchProvisionRequest(BaseModel):
    """Payload used to create one batch provisioning job."""

    resource_type: str = Field(..., pattern="^(lxc|qemu)$")
    hostname_prefix: str = Field(
        ..., min_length=1, max_length=50,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9-]*$",
        description="Hostname prefix: ASCII letters, digits, hyphens; cannot start with hyphen",
    )
    password: str = Field(..., min_length=6)
    cores: int = Field(2, ge=1, le=32)
    memory: int = Field(2048, ge=128, le=65536)
    environment_type: str = Field(default="批次部署")
    os_info: str | None = None
    expiry_date: date | None = None

    ostemplate: str | None = None
    rootfs_size: int | None = Field(default=8, ge=1, le=1000)

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


def _validate_request(body: BatchProvisionRequest) -> None:
    if body.resource_type == "lxc":
        if not body.ostemplate:
            raise BadRequestError("LXC batch provision requires ostemplate")
        return

    if not body.template_id:
        raise BadRequestError("VM batch provision requires template_id")
    if not body.username:
        raise BadRequestError("VM batch provision requires username")


def _require_group_job_access(
    *,
    session: SessionDep,
    current_user,
    group_id: uuid.UUID,
):
    db_group = group_repo.get_group_by_id(session=session, group_id=group_id)
    if not db_group:
        raise NotFoundError("Group not found")
    require_group_access(current_user, db_group.owner_id)
    return db_group


def _build_job_public(session: SessionDep, job) -> BatchProvisionJobPublic:
    tasks = bp_repo.get_job_tasks(session=session, job_id=job.id)

    user_ids = [task.user_id for task in tasks]
    users: dict[uuid.UUID, User] = {}
    if user_ids:
        rows = session.exec(select(User).where(User.id.in_(user_ids))).all()
        users = {user.id: user for user in rows}

    task_publics = [
        BatchProvisionTaskPublic(
            id=task.id,
            user_id=task.user_id,
            user_email=users[task.user_id].email if task.user_id in users else None,
            user_name=users[task.user_id].full_name if task.user_id in users else None,
            member_index=task.member_index,
            vmid=task.vmid,
            status=task.status,
            error=task.error,
            started_at=task.started_at,
            finished_at=task.finished_at,
        )
        for task in tasks
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


@router.post("/{group_id}", response_model=BatchProvisionJobPublic)
def start_batch_provision(
    group_id: uuid.UUID,
    body: BatchProvisionRequest,
    session: SessionDep,
    current_user: InstructorUser,
) -> BatchProvisionJobPublic:
    _validate_request(body)
    _require_group_job_access(
        session=session,
        current_user=current_user,
        group_id=group_id,
    )

    params = body.model_dump(
        exclude={"resource_type", "hostname_prefix"},
        exclude_none=False,
    )
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
    if not job:
        raise NotFoundError("Batch provision job not found")
    return _build_job_public(session, job)


@router.get("/{job_id}/status", response_model=BatchProvisionJobPublic)
def get_batch_status(
    job_id: uuid.UUID,
    session: SessionDep,
    current_user: InstructorUser,
) -> BatchProvisionJobPublic:
    job = bp_repo.get_job(session=session, job_id=job_id)
    if not job:
        raise NotFoundError("Batch provision job not found")
    _require_group_job_access(
        session=session,
        current_user=current_user,
        group_id=job.group_id,
    )
    return _build_job_public(session, job)


@router.get("/group/{group_id}", response_model=list[BatchProvisionJobPublic])
def list_group_jobs(
    group_id: uuid.UUID,
    session: SessionDep,
    current_user: InstructorUser,
) -> list[BatchProvisionJobPublic]:
    _require_group_job_access(
        session=session,
        current_user=current_user,
        group_id=group_id,
    )
    jobs = bp_repo.list_jobs_by_group(session=session, group_id=group_id)
    return [_build_job_public(session, job) for job in jobs]
