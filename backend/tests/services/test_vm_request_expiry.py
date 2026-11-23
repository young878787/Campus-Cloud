"""VM 申請逾時自動過期的測試。

過期規則：status == pending AND end_at IS NOT NULL AND end_at <= now。
過期只改 status，不碰任何審核欄位。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.models import (
    AuditAction,
    VMRequestStatus,
)
from app.schemas.jobs import JobStatus
from app.services.jobs import jobs_service
from app.services.scheduling import coordinator
from app.services.user import audit_service
from app.services.vm import vm_request_expiry_service


def test_expired_status_exists() -> None:
    assert VMRequestStatus.expired.value == "expired"


def test_expired_audit_action_exists_and_is_categorised() -> None:
    assert AuditAction.vm_request_expired.value == "vm_request_expired"
    # 漏掉分類會讓後台稽核頁的下拉分組落到 "other"。
    assert audit_service.ACTION_CATEGORY[AuditAction.vm_request_expired] == "request"


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


class _FakeSession:
    """站在 `with Session(engine) as session:` 位置的替身。"""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: Any) -> None:
        # 回傳 None（falsy）＝ 不吞例外，讓它照常往外傳。
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_process_expired_requests_marks_and_audits_each_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req_a = SimpleNamespace(id=uuid.uuid4(), end_at=NOW - timedelta(hours=1))
    req_b = SimpleNamespace(id=uuid.uuid4(), end_at=NOW - timedelta(days=1))
    fake_session = _FakeSession()
    monkeypatch.setattr(
        vm_request_expiry_service, "Session", lambda _engine: fake_session
    )

    marked: list[Any] = []
    monkeypatch.setattr(
        vm_request_expiry_service,
        "vm_request_repo",
        SimpleNamespace(
            list_expired_pending_vm_requests=lambda **kw: [req_a, req_b],
            mark_vm_request_expired=lambda **kw: marked.append(kw["db_request"]),
        ),
    )

    audited: list[dict[str, Any]] = []
    monkeypatch.setattr(
        vm_request_expiry_service,
        "audit_service",
        SimpleNamespace(log_action=lambda **kw: audited.append(kw)),
    )

    count = vm_request_expiry_service.process_expired_requests()

    assert count == 2
    assert marked == [req_a, req_b]
    assert [entry["action"] for entry in audited] == [
        AuditAction.vm_request_expired,
        AuditAction.vm_request_expired,
    ]
    # 系統動作，沒有操作者
    assert all(entry["user_id"] is None for entry in audited)
    # 整批一次 commit，避免中途釋放 FOR UPDATE 鎖
    assert fake_session.committed
    assert not fake_session.rolled_back


def test_process_expired_requests_is_noop_when_nothing_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _FakeSession()
    monkeypatch.setattr(
        vm_request_expiry_service, "Session", lambda _engine: fake_session
    )
    monkeypatch.setattr(
        vm_request_expiry_service,
        "vm_request_repo",
        SimpleNamespace(list_expired_pending_vm_requests=lambda **kw: []),
    )

    assert vm_request_expiry_service.process_expired_requests() == 0
    assert not fake_session.committed


def test_process_expired_requests_rolls_back_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req = SimpleNamespace(id=uuid.uuid4(), end_at=NOW - timedelta(hours=1))
    fake_session = _FakeSession()
    monkeypatch.setattr(
        vm_request_expiry_service, "Session", lambda _engine: fake_session
    )

    def _boom(**kw: Any) -> None:
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(
        vm_request_expiry_service,
        "vm_request_repo",
        SimpleNamespace(
            list_expired_pending_vm_requests=lambda **kw: [req],
            mark_vm_request_expired=_boom,
        ),
    )
    monkeypatch.setattr(
        vm_request_expiry_service,
        "audit_service",
        SimpleNamespace(log_action=lambda **kw: None),
    )

    # tick 不該把例外往上拋，否則整個 scheduler 迴圈會被打斷
    assert vm_request_expiry_service.process_expired_requests() == 0
    assert fake_session.rolled_back
    assert not fake_session.committed


def test_coordinator_task_delegates_to_expiry_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def _fake_process() -> int:
        calls.append(True)
        return 3

    monkeypatch.setattr(
        vm_request_expiry_service, "process_expired_requests", _fake_process
    )

    assert coordinator.process_expired_requests_task() == 3
    assert calls == [True]


def test_every_vm_request_status_maps_to_a_job_status() -> None:
    """查表用 .get() 帶預設值，缺鍵會靜默顯示成「等待中」而不是報錯。"""
    missing = [
        status.value
        for status in VMRequestStatus
        if status not in jobs_service._VM_REQUEST_STATUS_MAP
    ]
    assert missing == []


def test_expired_request_maps_to_cancelled_job() -> None:
    # 什麼都沒失敗，申請只是失效了 —— 語意上貼近 cancelled 而非 failed。
    assert (
        jobs_service._VM_REQUEST_STATUS_MAP[VMRequestStatus.expired]
        == JobStatus.cancelled
    )
