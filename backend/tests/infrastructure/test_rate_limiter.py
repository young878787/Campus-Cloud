"""app/infrastructure/redis/rate_limiter.py 在 Redis 不可用時的 fail-closed 政策：認證與 AI proxy 配額拒絕，其他 scope 放行；本機環境全部放行。"""

from __future__ import annotations

import pytest

from app.exceptions import AppError
from app.infrastructure.redis import rate_limiter


def _fatal(monkeypatch: pytest.MonkeyPatch, module, value: bool) -> None:
    monkeypatch.setattr(module, "redis_failures_are_fatal", lambda: value)


# ── 1. Redis fail-closed ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_scope_rejects_when_redis_unavailable_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fatal(monkeypatch, rate_limiter, True)
    with pytest.raises(AppError) as exc_info:
        await rate_limiter.check_rate_limit_by_key(
            None, key="ip:login:1.2.3.4", limit=10, window_seconds=60, scope="login"
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_other_scopes_still_pass_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fatal(monkeypatch, rate_limiter, True)
    allowed, info = await rate_limiter.check_rate_limit_by_key(
        None,
        key="user:vm-request-create:1",
        limit=10,
        window_seconds=60,
        scope="vm-request-create",
    )
    assert allowed is True
    assert info["disabled"] is True


@pytest.mark.asyncio
async def test_local_allows_every_scope_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fatal(monkeypatch, rate_limiter, False)
    allowed, _ = await rate_limiter.check_rate_limit_by_key(
        None, key="ip:login:1.2.3.4", limit=10, window_seconds=60, scope="login"
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_ai_proxy_quota_rejects_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fatal(monkeypatch, rate_limiter, True)
    with pytest.raises(AppError):
        await rate_limiter.check_rate_limit_sliding_window(None, "user-1", limit=20)
