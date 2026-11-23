"""重置重複入列檢查要能讀 ORM 回傳的 dict payload。

TaskRecord.payload 是 JSON 欄位，真實資料庫讀回來是 dict。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.exceptions import ConflictError
from app.models.task_record import TaskRecord, TaskRecordStatus
from app.services.resource import reset_service


class _Session:
    def __init__(self, records: list[TaskRecord]) -> None:
        self.records = records
        self.rolled_back = False

    def exec(self, stmt: Any) -> Any:
        return SimpleNamespace(all=lambda: self.records)

    def add(self, obj: Any) -> None:
        """測試替身。"""

    def commit(self) -> None:
        """測試替身。"""

    def rollback(self) -> None:
        self.rolled_back = True


def _record(
    payload: Any, status: TaskRecordStatus = TaskRecordStatus.queued
) -> TaskRecord:
    return TaskRecord(
        task_type=reset_service.TASK_RESET,
        user_id=uuid.uuid4(),
        payload=payload,
        status=status,
    )


def test_dict_payload_is_detected() -> None:
    session = _Session([_record({"vmid": 101, "node": "pve1", "rtype": "qemu"})])

    assert reset_service._has_active_reset(session, 101) is True  # type: ignore[arg-type]
    assert reset_service._has_active_reset(session, 102) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("task_type", ["resource.backup", "resource.restore"])
def test_start_reset_rejected_while_backup_or_restore_active(
    monkeypatch: pytest.MonkeyPatch, task_type: str
) -> None:
    """備份／還原進行中也不能重置：兩者並行會讀到錯的電源狀態或 rollback 失敗。"""
    monkeypatch.setattr(reset_service, "require_snapshot_available", lambda *_: None)
    monkeypatch.setattr(reset_service, "_has_init_snapshot", lambda *_: True)
    # 替身 session 不套 WHERE，這裡明確表示「沒有進行中的重置」
    monkeypatch.setattr(reset_service, "_has_active_reset", lambda *_: False)
    monkeypatch.setattr(reset_service.audit_service, "log_action", lambda **_: None)
    enqueued: list[Any] = []
    monkeypatch.setattr(
        reset_service, "enqueue_task_sync", lambda **kw: enqueued.append(kw)
    )
    active = TaskRecord(
        task_type=task_type,
        user_id=uuid.uuid4(),
        payload={"vmid": 101},
        status=TaskRecordStatus.running,
    )
    session = _Session([active])

    with pytest.raises(ConflictError):
        reset_service.start_reset(
            session,  # type: ignore[arg-type]
            vmid=101,
            resource_info={"node": "pve1", "type": "qemu"},
            user=SimpleNamespace(id=uuid.uuid4()),
        )

    assert enqueued == []
    assert session.rolled_back is True
