"""已核准但始終沒開出機器的申請：時段內佔配額，時段結束就過期並釋放。

- 時段內（end_at 未到）照常計入配額
- 時段結束、沒有 vmid → 排程標成 expired，配額不再計入
- clone 正在跑的不動；沒有結束時間（immediate 模式）的保守地一直計入
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.models import (
    AuditAction,
    VMProvisioningStatus,
)
from app.services.scheduling import coordinator
from app.services.vm import vm_request_expiry_service


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_expiry_marks_unprovisioned_requests_but_not_inflight_clones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    failed = SimpleNamespace(
        id=uuid.uuid4(),
        end_at=now - timedelta(hours=1),
        provisioning_status=VMProvisioningStatus.failed,
        provisioning_started_at=None,
    )
    stale_running = SimpleNamespace(
        id=uuid.uuid4(),
        end_at=now - timedelta(hours=1),
        provisioning_status=VMProvisioningStatus.running,
        provisioning_started_at=now - timedelta(days=1),
    )
    cloning = SimpleNamespace(
        id=uuid.uuid4(),
        end_at=now - timedelta(minutes=1),
        provisioning_status=VMProvisioningStatus.running,
        provisioning_started_at=now - timedelta(minutes=2),
    )
    fake_session = _FakeSession()
    monkeypatch.setattr(
        vm_request_expiry_service, "Session", lambda _engine: fake_session
    )
    marked: list[Any] = []
    monkeypatch.setattr(
        vm_request_expiry_service,
        "vm_request_repo",
        SimpleNamespace(
            list_expired_unprovisioned_approved_vm_requests=lambda **kw: [
                failed,
                stale_running,
                cloning,
            ],
            mark_vm_request_expired=lambda **kw: marked.append(kw["db_request"]),
        ),
    )
    audited: list[dict[str, Any]] = []
    monkeypatch.setattr(
        vm_request_expiry_service,
        "audit_service",
        SimpleNamespace(log_action=lambda **kw: audited.append(kw)),
    )

    assert vm_request_expiry_service.process_expired_unprovisioned_requests() == 2

    assert marked == [failed, stale_running]
    assert [entry["action"] for entry in audited] == [
        AuditAction.vm_request_expired,
        AuditAction.vm_request_expired,
    ]
    assert fake_session.committed


def test_expiry_of_unprovisioned_requests_rolls_back_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        end_at=datetime.now(UTC) - timedelta(hours=1),
        provisioning_status=VMProvisioningStatus.failed,
        provisioning_started_at=None,
    )
    fake_session = _FakeSession()
    monkeypatch.setattr(
        vm_request_expiry_service, "Session", lambda _engine: fake_session
    )

    def boom(**_kw: Any) -> None:
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(
        vm_request_expiry_service,
        "vm_request_repo",
        SimpleNamespace(
            list_expired_unprovisioned_approved_vm_requests=lambda **kw: [row],
            mark_vm_request_expired=boom,
        ),
    )
    monkeypatch.setattr(
        vm_request_expiry_service,
        "audit_service",
        SimpleNamespace(log_action=lambda **kw: None),
    )

    assert vm_request_expiry_service.process_expired_unprovisioned_requests() == 0
    assert fake_session.rolled_back
    assert not fake_session.committed


def test_coordinator_runs_unprovisioned_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vm_request_expiry_service,
        "process_expired_unprovisioned_requests",
        lambda: 4,
    )

    assert coordinator.process_expired_unprovisioned_requests_task() == 4
