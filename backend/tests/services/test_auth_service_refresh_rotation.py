"""app/services/user/auth_service.py 的 refresh_access_token：已輪替的 refresh token 必須拒絕，首次兌換成功並記錄使用。"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import jwt
import pytest

import app.infrastructure.redis as redis_module
from app.core import security
from app.core.config import settings
from app.exceptions import AuthenticationError
from app.services.user import auth_service

_USER_ID = uuid.uuid4()


class _FakeRedis:
    """只支援本測試用到的 set(nx/ex) / get / exists。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def exists(self, key: str) -> int:
        return int(key in self.store)


def _make_refresh_token(*, jti: str) -> str:
    payload: dict[str, Any] = {
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        "sub": str(_USER_ID),
        "type": "refresh",
        "ver": 0,
        "jti": jti,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=security.ALGORITHM)


class _FakeSession:
    def __init__(self, user: Any) -> None:
        self._user = user

    def get(self, model: Any, key: Any) -> Any:
        return self._user


async def test_refresh_access_token_rejects_rotated_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    fake_redis.store["refresh_used:old-jti"] = str(int(time.time()) - 600)

    async def fake_get_redis() -> _FakeRedis:
        return fake_redis

    monkeypatch.setattr(redis_module, "get_redis", fake_get_redis)
    session = _FakeSession(
        SimpleNamespace(id=_USER_ID, token_version=0, is_active=True)
    )

    with pytest.raises(AuthenticationError):
        await auth_service.refresh_access_token(
            session=session, refresh_token=_make_refresh_token(jti="old-jti")
        )


async def test_refresh_access_token_first_exchange_succeeds_and_records_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()

    async def fake_get_redis() -> _FakeRedis:
        return fake_redis

    monkeypatch.setattr(redis_module, "get_redis", fake_get_redis)
    session = _FakeSession(
        SimpleNamespace(id=_USER_ID, token_version=0, is_active=True)
    )

    token = await auth_service.refresh_access_token(
        session=session, refresh_token=_make_refresh_token(jti="fresh-jti")
    )
    assert token.access_token
    assert "refresh_used:fresh-jti" in fake_redis.store
