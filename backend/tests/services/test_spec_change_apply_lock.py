"""app/services/vm/spec_change_service.py 的套用鎖（_apply_recently_started）：視窗內擋重複套用、過期或失敗後放行，並接受 SQLite 回傳的 naive 時間。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from app.services.vm import spec_change_service

# ---------------------------------------------------------------------------
# 規格調整：重複套用的 DB 鎖（background_tasks.is_active 只認本行程）
# ---------------------------------------------------------------------------


def _spec_request(**kwargs: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "applied_at": None,
        "apply_error": None,
        "apply_started_at": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_apply_recently_started_blocks_second_apply() -> None:
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert spec_change_service._apply_recently_started(
        _spec_request(apply_started_at=started)
    )


def test_apply_recently_started_expires_after_lock_window() -> None:
    started = datetime.now(timezone.utc) - timedelta(
        minutes=spec_change_service.APPLY_LOCK_MINUTES + 1
    )
    assert not spec_change_service._apply_recently_started(
        _spec_request(apply_started_at=started)
    )


def test_apply_recently_started_allows_retry_after_failure() -> None:
    started = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert not spec_change_service._apply_recently_started(
        _spec_request(apply_started_at=started, apply_error="boom")
    )


def test_apply_recently_started_handles_naive_timestamp() -> None:
    """SQLite 取回的時間沒有 tzinfo，不可以因此炸掉。"""
    started = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    assert spec_change_service._apply_recently_started(
        _spec_request(apply_started_at=started)
    )
