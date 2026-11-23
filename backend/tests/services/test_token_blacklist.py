"""Tests for the Redis-backed JWT revocation blacklist.

Uses a real Redis client (skipped if unavailable) to verify that
revoke→check round-trips behave correctly and that TTL is honoured.
"""

from __future__ import annotations

import time

import pytest

redis_asyncio = pytest.importorskip("redis.asyncio")
Redis = redis_asyncio.Redis

# 連真 Redis 並 flushdb：CI 只在序列的 integration job 執行
pytestmark = pytest.mark.integration

from app.infrastructure.redis.token_blacklist import is_jti_revoked, revoke_jti


@pytest.fixture
async def redis_client():
    from app.features.ai.config import settings

    client = Redis.from_url(settings.redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.mark.asyncio
async def test_revoke_then_check_returns_true(redis_client: Redis) -> None:
    exp = int(time.time()) + 60
    ok = await revoke_jti(redis_client, "abc123", exp)
    assert ok is True
    assert await is_jti_revoked(redis_client, "abc123") is True


@pytest.mark.asyncio
async def test_check_unrevoked_returns_false(redis_client: Redis) -> None:
    assert await is_jti_revoked(redis_client, "never-seen") is False


@pytest.mark.asyncio
async def test_revoke_with_past_exp_is_noop(redis_client: Redis) -> None:
    past = int(time.time()) - 10
    ok = await revoke_jti(redis_client, "expired", past)
    assert ok is False
    assert await is_jti_revoked(redis_client, "expired") is False


@pytest.mark.asyncio
async def test_revoke_with_none_redis_fails_open() -> None:
    """When Redis is disabled, revocation is a no-op and check returns False."""
    assert await revoke_jti(None, "x", int(time.time()) + 60) is False
    assert await is_jti_revoked(None, "x") is False


@pytest.mark.asyncio
async def test_ttl_aligned_to_token_expiry(redis_client: Redis) -> None:
    exp = int(time.time()) + 30
    await revoke_jti(redis_client, "ttl-check", exp)
    ttl = await redis_client.ttl("revoked_jti:ttl-check")
    assert 1 <= ttl <= 30
