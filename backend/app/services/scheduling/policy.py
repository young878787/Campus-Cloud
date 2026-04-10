from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import uuid

from sqlmodel import Session

from app.models import VMRequest
from app.repositories import proxmox_config as proxmox_config_repo

SCHEDULER_POLL_SECONDS = 60


@dataclass(frozen=True)
class MigrationPolicy:
    enabled: bool
    max_per_rebalance: int
    min_interval_minutes: int
    retry_limit: int
    worker_concurrency: int
    claim_timeout_seconds: int
    retry_backoff_seconds: int
    lxc_live_enabled: bool = False


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def resource_type_for_request(request: VMRequest) -> str:
    return "lxc" if request.resource_type == "lxc" else "qemu"


def get_migration_policy(*, session: Session) -> MigrationPolicy:
    config = proxmox_config_repo.get_proxmox_config(session)
    if config is None:
        return MigrationPolicy(
            enabled=True,
            max_per_rebalance=2,
            min_interval_minutes=60,
            retry_limit=3,
            worker_concurrency=2,
            claim_timeout_seconds=300,
            retry_backoff_seconds=120,
            lxc_live_enabled=False,
        )
    return MigrationPolicy(
        enabled=bool(config.migration_enabled),
        max_per_rebalance=max(int(config.migration_max_per_rebalance or 0), 0),
        min_interval_minutes=max(int(config.migration_min_interval_minutes or 0), 0),
        retry_limit=max(int(config.migration_retry_limit or 0), 0),
        worker_concurrency=max(int(config.migration_worker_concurrency or 2), 1),
        claim_timeout_seconds=max(
            int(config.migration_job_claim_timeout_seconds or 300),
            30,
        ),
        retry_backoff_seconds=max(
            int(config.migration_retry_backoff_seconds or 120),
            0,
        ),
        lxc_live_enabled=bool(config.migration_lxc_live_enabled),
    )


def migration_worker_id() -> str:
    return f"scheduler-{uuid.uuid4()}"


def next_retry_at(
    *,
    now: datetime,
    policy: MigrationPolicy,
    attempt_count: int,
) -> datetime:
    base_seconds = max(policy.retry_backoff_seconds, SCHEDULER_POLL_SECONDS)
    exponent = max(int(attempt_count) - 1, 0)
    return now + timedelta(seconds=base_seconds * (2**exponent))
