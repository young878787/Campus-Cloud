"""app/repositories/push.py 的 upsert_subscription 歸屬規則：同一 endpoint 且金鑰相符時才能接手既有訂閱，金鑰不符時不得改寫原擁有者的訂閱。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.repositories import push as push_repo

# ── 8. 推播訂閱不可被搶走 ───────────────────────────────────────────────────


class _FakeSession:
    def __init__(self) -> None:
        self.deleted: list[object] = []
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def delete(self, obj: object) -> None:
        self.deleted.append(obj)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def refresh(self, obj: object) -> None:
        pass


def _existing(user_id: uuid.UUID, *, p256dh: str = "p", auth: str = "a"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        endpoint="https://push.example/x",
        p256dh=p256dh,
        auth=auth,
        user_agent=None,
        language="zh-TW",
        failure_count=3,
        last_seen_at=None,
    )


def test_matching_browser_keys_may_take_over_the_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_owner = uuid.uuid4()
    new_owner = uuid.uuid4()
    existing = _existing(previous_owner)
    monkeypatch.setattr(
        push_repo,
        "get_subscription_by_endpoint",
        lambda *, session, endpoint: existing,
    )
    session = _FakeSession()
    result = push_repo.upsert_subscription(
        session=session,  # type: ignore[arg-type]
        user_id=new_owner,
        endpoint="https://push.example/x",
        p256dh="p",
        auth="a",
        user_agent=None,
        language="zh-TW",
    )
    assert result is existing
    assert result.user_id == new_owner
    assert session.deleted == []


def test_mismatched_keys_cannot_steal_someone_elses_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = uuid.uuid4()
    attacker = uuid.uuid4()
    existing = _existing(victim)
    monkeypatch.setattr(
        push_repo,
        "get_subscription_by_endpoint",
        lambda *, session, endpoint: existing,
    )
    session = _FakeSession()
    result = push_repo.upsert_subscription(
        session=session,  # type: ignore[arg-type]
        user_id=attacker,
        endpoint="https://push.example/x",
        p256dh="other-p256dh",
        auth="other-auth",
        user_agent=None,
        language="zh-TW",
    )
    # 舊列被刪掉、另建一筆新的；受害者的訂閱不會被改歸屬
    assert existing.user_id == victim
    assert session.deleted == [existing]
    assert result is not existing
    assert result.user_id == attacker
