"""app/infrastructure/redis/token_blacklist.py 的 refresh token 輪替：首次使用與寬限期內重用放行，超過寬限期的重用拒絕，無 Redis 時 fail-open。"""

from __future__ import annotations

import time

from app.infrastructure.redis.token_blacklist import mark_refresh_token_used


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


# ---------------------------------------------------------------------------
# refresh token rotation
# ---------------------------------------------------------------------------


async def test_mark_refresh_token_used_allows_first_use_and_grace_window() -> None:
    redis = _FakeRedis()
    exp = int(time.time()) + 3600

    assert await mark_refresh_token_used(redis, "jti-1", exp) is True
    # 寬限期內（多分頁競態）仍允許
    assert await mark_refresh_token_used(redis, "jti-1", exp) is True


async def test_mark_refresh_token_used_rejects_stale_reuse() -> None:
    redis = _FakeRedis()
    exp = int(time.time()) + 3600
    redis.store["refresh_used:jti-2"] = str(int(time.time()) - 600)

    assert await mark_refresh_token_used(redis, "jti-2", exp) is False


async def test_mark_refresh_token_used_fails_open_without_redis() -> None:
    assert await mark_refresh_token_used(None, "jti-3", int(time.time()) + 60) is True
