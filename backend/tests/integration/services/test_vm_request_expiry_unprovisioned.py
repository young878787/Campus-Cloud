"""已核准但始終沒開出機器的申請：時段結束就過期並釋放配額（需真 Postgres 的整合測試）。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.models import User, VMProvisioningStatus, VMRequest, VMRequestStatus
from app.repositories import vm_request as vm_request_repo
from app.services.resource import quota_service


def _db_fixture_available() -> bool:
    from tests.conftest import _assert_safe_pytest_database_target

    try:
        _assert_safe_pytest_database_target()
    except RuntimeError:
        return False
    return True


requires_test_db = pytest.mark.skipif(
    not _db_fixture_available(),
    reason="需要測試用資料庫（見 tests/conftest.py 的 _assert_safe_pytest_database_target）",
)


NOW = datetime.now(UTC)


def _row(
    user_id: uuid.UUID,
    *,
    status: VMRequestStatus = VMRequestStatus.approved,
    end_at: datetime | None,
    vmid: int | None = None,
    provisioning_status: VMProvisioningStatus = VMProvisioningStatus.failed,
    provisioning_started_at: datetime | None = None,
) -> VMRequest:
    return VMRequest(
        user_id=user_id,
        reason="unprovisioned expiry test",
        resource_type="lxc",
        hostname=f"unprov-{uuid.uuid4().hex[:8]}",
        password="encrypted-placeholder",
        cores=2,
        memory=2048,
        rootfs_size=10,
        status=status,
        vmid=vmid,
        provisioning_status=provisioning_status,
        provisioning_started_at=provisioning_started_at,
        start_at=NOW - timedelta(days=2),
        end_at=end_at,
        created_at=NOW - timedelta(days=3),
    )


def _superuser_id(db: Session) -> uuid.UUID:
    return db.exec(select(User).where(User.email == settings.FIRST_SUPERUSER)).one().id


@requires_test_db
def test_only_unprovisioned_approved_requests_past_end_are_selected(db: Session) -> None:
    user_id = _superuser_id(db)
    ended = _row(user_id, end_at=NOW - timedelta(hours=1))
    in_window = _row(user_id, end_at=NOW + timedelta(hours=1))
    open_ended = _row(user_id, end_at=None)
    provisioned = _row(user_id, end_at=NOW - timedelta(hours=1), vmid=987654)
    pending = _row(
        user_id, status=VMRequestStatus.pending, end_at=NOW - timedelta(hours=1)
    )

    try:
        db.add_all([ended, in_window, open_ended, provisioned, pending])
        db.flush()

        picked = {
            row.id
            for row in vm_request_repo.list_expired_unprovisioned_approved_vm_requests(
                session=db, at_time=NOW, limit=1000
            )
        }

        assert ended.id in picked
        assert in_window.id not in picked
        # immediate 模式沒有結束時間，沒有時段可結束
        assert open_ended.id not in picked
        # 已開出機器的由 process_due_request_stops 管
        assert provisioned.id not in picked
        # pending 走既有的 list_expired_pending_vm_requests
        assert pending.id not in picked
    finally:
        db.rollback()


@requires_test_db
def test_quota_releases_unprovisioned_request_only_after_window_ends(
    db: Session,
) -> None:
    user_id = _superuser_id(db)
    rows = {
        "ended": _row(user_id, end_at=NOW - timedelta(hours=1)),
        "in_window": _row(user_id, end_at=NOW + timedelta(hours=1)),
        "open_ended": _row(user_id, end_at=None),
        "ended_but_cloning": _row(
            user_id,
            end_at=NOW - timedelta(minutes=1),
            provisioning_status=VMProvisioningStatus.running,
            provisioning_started_at=NOW - timedelta(minutes=5),
        ),
        "pending_ended": _row(
            user_id, status=VMRequestStatus.pending, end_at=NOW - timedelta(hours=1)
        ),
    }

    try:
        db.add_all(rows.values())
        db.flush()

        # 以「排除某一張後少不少一張」比較，不受資料庫裡其他申請影響
        def reserved_count(exclude: uuid.UUID | None = None) -> int:
            return quota_service._reserved_by_requests(
                db, user_id, exclude_request_id=exclude
            )[3]

        total = reserved_count()
        # 時段內、沒有結束時間、clone 正在跑的都要算；時段已過的兩張不算
        for counted in ("in_window", "open_ended", "ended_but_cloning"):
            assert reserved_count(rows[counted].id) == total - 1
        for released in ("ended", "pending_ended"):
            assert reserved_count(rows[released].id) == total
    finally:
        db.rollback()
