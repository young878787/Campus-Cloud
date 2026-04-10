"""Migration job management API routes."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import AdminUser, SessionDep
from app.models import AuditAction, VMMigrationJob, VMMigrationJobStatus
from app.repositories import vm_migration_job as vm_migration_job_repo
from app.services.user import audit_service

router = APIRouter(prefix="/migration-jobs", tags=["migration-jobs"])


class MigrationJobPublic(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    vmid: int | None = None
    source_node: str | None = None
    target_node: str
    status: VMMigrationJobStatus
    rebalance_epoch: int = 0
    attempt_count: int = 0
    last_error: str | None = None
    requested_at: datetime
    available_at: datetime | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class MigrationJobsPublic(BaseModel):
    data: list[MigrationJobPublic]
    count: int


class MigrationStatsPublic(BaseModel):
    total_jobs: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    avg_duration_seconds: float = 0.0
    success_rate: float = 0.0


def _job_to_public(job: VMMigrationJob) -> MigrationJobPublic:
    return MigrationJobPublic(
        id=job.id,
        request_id=job.request_id,
        vmid=job.vmid,
        source_node=job.source_node,
        target_node=job.target_node,
        status=job.status,
        rebalance_epoch=job.rebalance_epoch,
        attempt_count=job.attempt_count,
        last_error=job.last_error,
        requested_at=job.requested_at,
        available_at=job.available_at,
        claimed_by=job.claimed_by,
        claimed_at=job.claimed_at,
        claim_expires_at=job.claim_expires_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        updated_at=job.updated_at,
    )


@router.get("/", response_model=MigrationJobsPublic)
def list_migration_jobs(
    session: SessionDep,
    current_user: AdminUser,
    status: VMMigrationJobStatus | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    jobs, total = vm_migration_job_repo.list_all_jobs(
        session=session,
        status=status,
        skip=skip,
        limit=limit,
    )
    return MigrationJobsPublic(
        data=[_job_to_public(job) for job in jobs],
        count=total,
    )


@router.get("/stats", response_model=MigrationStatsPublic)
def get_migration_stats(
    session: SessionDep,
    current_user: AdminUser,
):
    stats = vm_migration_job_repo.get_migration_stats(session=session)
    return MigrationStatsPublic(**stats)


@router.get("/{job_id}", response_model=MigrationJobPublic)
def get_migration_job(
    job_id: uuid.UUID,
    session: SessionDep,
    current_user: AdminUser,
):
    job = vm_migration_job_repo.get_job_by_id(session=session, job_id=job_id)
    if job is None:
        from app.exceptions import NotFoundError
        raise NotFoundError(f"Migration job {job_id} not found")
    return _job_to_public(job)


@router.post("/{job_id}/retry", response_model=MigrationJobPublic)
def retry_migration_job(
    job_id: uuid.UUID,
    session: SessionDep,
    current_user: AdminUser,
):
    job = vm_migration_job_repo.get_job_by_id(session=session, job_id=job_id)
    if job is None:
        from app.exceptions import NotFoundError
        raise NotFoundError(f"Migration job {job_id} not found")
    if job.status not in {
        VMMigrationJobStatus.failed,
        VMMigrationJobStatus.blocked,
        VMMigrationJobStatus.cancelled,
    }:
        from app.exceptions import PermissionDeniedError
        raise PermissionDeniedError(
            f"Cannot retry job in '{job.status}' status. "
            "Only failed, blocked, or cancelled jobs can be retried."
        )
    now = datetime.now(timezone.utc)
    updated = vm_migration_job_repo.update_job_status(
        session=session,
        job=job,
        status=VMMigrationJobStatus.pending,
        last_error=f"Manually retried by {current_user.email}",
        available_at=now,
        finished_at=None,
        commit=True,
    )
    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        vmid=job.vmid,
        action=AuditAction.migration_job_retry,
        details=(
            f"Retried migration job {job_id} (vmid={job.vmid}, "
            f"target={job.target_node})"
        ),
    )
    return _job_to_public(updated)


@router.post("/{job_id}/cancel", response_model=MigrationJobPublic)
def cancel_migration_job(
    job_id: uuid.UUID,
    session: SessionDep,
    current_user: AdminUser,
):
    job = vm_migration_job_repo.get_job_by_id(session=session, job_id=job_id)
    if job is None:
        from app.exceptions import NotFoundError
        raise NotFoundError(f"Migration job {job_id} not found")
    if job.status not in {
        VMMigrationJobStatus.pending,
        VMMigrationJobStatus.blocked,
        VMMigrationJobStatus.failed,
    }:
        from app.exceptions import PermissionDeniedError
        raise PermissionDeniedError(
            f"Cannot cancel job in '{job.status}' status. "
            "Only pending, blocked, or failed jobs can be cancelled."
        )
    now = datetime.now(timezone.utc)
    updated = vm_migration_job_repo.update_job_status(
        session=session,
        job=job,
        status=VMMigrationJobStatus.cancelled,
        last_error=f"Manually cancelled by {current_user.email}",
        finished_at=now,
        commit=True,
    )
    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        vmid=job.vmid,
        action=AuditAction.migration_job_cancel,
        details=(
            f"Cancelled migration job {job_id} (vmid={job.vmid}, "
            f"target={job.target_node})"
        ),
    )
    return _job_to_public(updated)
