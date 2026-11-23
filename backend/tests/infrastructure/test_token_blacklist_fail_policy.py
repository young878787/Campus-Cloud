"""app/infrastructure/redis/token_blacklist.py 在 Redis 不可用時的 fail-closed／fail-open 政策：非本機環境視為已撤銷並拒絕 refresh token 重用，本機環境放行。"""

from __future__ import annotations

import pytest

from app.infrastructure.redis import token_blacklist


def _fatal(monkeypatch: pytest.MonkeyPatch, module, value: bool) -> None:
    monkeypatch.setattr(module, "redis_failures_are_fatal", lambda: value)


@pytest.mark.asyncio
async def test_revocation_check_fails_closed_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fatal(monkeypatch, token_blacklist, True)
    assert await token_blacklist.is_jti_revoked(None, "jti-1") is True
    assert await token_blacklist.mark_refresh_token_used(None, "jti-1", 2**31) is False


@pytest.mark.asyncio
async def test_revocation_check_fails_open_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fatal(monkeypatch, token_blacklist, False)
    assert await token_blacklist.is_jti_revoked(None, "jti-1") is False
    assert await token_blacklist.mark_refresh_token_used(None, "jti-1", 2**31) is True
