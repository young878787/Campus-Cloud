"""
Redis Rate Limiter 測試
"""

from datetime import datetime

import pytest

redis_asyncio = pytest.importorskip("redis.asyncio")
Redis = redis_asyncio.Redis

# 連真 Redis 並 flushdb：CI 只在序列的 integration job 執行
pytestmark = pytest.mark.integration

from app.infrastructure.redis import rate_limiter as rate_limiter_module
from app.infrastructure.redis.rate_limiter import check_rate_limit_sliding_window


@pytest.fixture
async def redis_client():
    """創建 Redis 測試客戶端"""
    from app.features.ai.config import settings

    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    # 清理測試數據
    await redis.flushdb()

    yield redis

    # 清理測試數據
    await redis.flushdb()
    await redis.aclose()


class FakeClock:
    """可手動推進的假時鐘，用來取代真實 sleep"""

    def __init__(self, start: float = 1_700_000_000.0):
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """只替換 rate_limiter 模組內的 time，不動全域 time.time"""
    clock = FakeClock()
    monkeypatch.setattr(rate_limiter_module, "time", clock)
    return clock


@pytest.mark.asyncio
async def test_rate_limit_allows_within_limit(redis_client: Redis):
    """測試：在限制內應該允許"""
    user_id = "test-user-1"

    # 發送 19 個請求（限制 20）
    for i in range(19):
        allowed, info = await check_rate_limit_sliding_window(
            redis_client, user_id, limit=20, window_seconds=60
        )
        assert allowed is True
        assert info["remaining"] == 20 - i - 1
        assert info["limit"] == 20
        assert info["current"] == i + 1


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_limit(redis_client: Redis):
    """測試：超過限制應該拒絕"""
    user_id = "test-user-2"

    # 發送 20 個請求
    for i in range(20):
        allowed, info = await check_rate_limit_sliding_window(
            redis_client, user_id, limit=20, window_seconds=60
        )
        assert allowed is True
        assert info["current"] == i + 1

    # 第 21 個應該被拒絕
    allowed, info = await check_rate_limit_sliding_window(
        redis_client, user_id, limit=20, window_seconds=60
    )
    assert allowed is False
    assert info["remaining"] == 0
    assert info["current"] == 20


@pytest.mark.asyncio
async def test_sliding_window_accuracy(redis_client: Redis, fake_clock: FakeClock):
    """測試：滑動窗口的精準性"""
    user_id = "test-user-3"

    # T0: 發送 20 個請求
    for _ in range(20):
        allowed, _ = await check_rate_limit_sliding_window(
            redis_client, user_id, limit=20, window_seconds=5
        )
        assert allowed is True

    # T0: 應該被拒絕
    allowed, info = await check_rate_limit_sliding_window(
        redis_client, user_id, limit=20, window_seconds=5
    )
    assert allowed is False
    assert info["current"] == 20

    # 前進 5.5 秒（窗口 5 秒，多留 0.5 秒餘裕，避免落在邊界）
    fake_clock.advance(5.5)

    # T+5.5s: 應該允許（舊請求已移出窗口）
    allowed, info = await check_rate_limit_sliding_window(
        redis_client, user_id, limit=20, window_seconds=5
    )
    assert allowed is True
    assert info["current"] == 1  # 只有這個新請求


@pytest.mark.asyncio
async def test_rate_limit_different_users(redis_client: Redis):
    """測試：不同用戶的限制是獨立的"""
    user1 = "test-user-4"
    user2 = "test-user-5"

    # 用戶 1 發送 20 個請求
    for _ in range(20):
        allowed, _ = await check_rate_limit_sliding_window(
            redis_client, user1, limit=20, window_seconds=60
        )
        assert allowed is True

    # 用戶 1 應該被拒絕
    allowed, _ = await check_rate_limit_sliding_window(
        redis_client, user1, limit=20, window_seconds=60
    )
    assert allowed is False

    # 用戶 2 應該仍然可以發送
    allowed, info = await check_rate_limit_sliding_window(
        redis_client, user2, limit=20, window_seconds=60
    )
    assert allowed is True
    assert info["current"] == 1


@pytest.mark.asyncio
async def test_rate_limit_info_structure(redis_client: Redis):
    """測試：返回的資訊結構正確"""
    user_id = "test-user-7"

    allowed, info = await check_rate_limit_sliding_window(
        redis_client, user_id, limit=20, window_seconds=60
    )

    assert allowed is True
    assert "limit" in info
    assert "current" in info
    assert "remaining" in info
    assert "reset_at" in info
    assert "window_seconds" in info

    assert info["limit"] == 20
    assert info["current"] == 1
    assert info["remaining"] == 19
    assert info["window_seconds"] == 60
    assert isinstance(info["reset_at"], datetime)


@pytest.mark.asyncio
async def test_rate_limit_partial_window(redis_client: Redis, fake_clock: FakeClock):
    """測試：部分窗口過期後恢復配額"""
    user_id = "test-user-8"

    # T0: 發送 10 個請求
    for _ in range(10):
        await check_rate_limit_sliding_window(
            redis_client, user_id, limit=20, window_seconds=3
        )

    # 前進 1 秒
    fake_clock.advance(1)

    # T+1s: 再發送 10 個請求
    for i in range(10):
        allowed, info = await check_rate_limit_sliding_window(
            redis_client, user_id, limit=20, window_seconds=3
        )
        assert allowed is True
        assert info["current"] == 10 + i + 1

    # T+1s: 應該被拒絕（20 個請求都在窗口內）
    allowed, _ = await check_rate_limit_sliding_window(
        redis_client, user_id, limit=20, window_seconds=3
    )
    assert allowed is False

    # 再前進 2.5 秒，共 T+3.5s：第一批（T0）已超出 3 秒窗口 0.5 秒，
    # 第二批（T+1s）仍在窗口內，避免兩批都落在邊界上
    fake_clock.advance(2.5)

    # T+3.5s: 第一批 10 個請求已經移出，應該可以發送
    allowed, info = await check_rate_limit_sliding_window(
        redis_client, user_id, limit=20, window_seconds=3
    )
    assert allowed is True
    # 窗口內只剩下第二批 10 個請求，加上本次應為 11
    assert info["current"] <= 11
