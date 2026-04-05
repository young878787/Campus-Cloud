"""
Redis Rate Limiter 服務

使用 Sliding Window Counter 算法實現精準的速率限制
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


async def check_rate_limit_sliding_window(
    redis: Redis | None,
    user_id: str,
    limit: int = 20,
    window_seconds: int = 60,
) -> tuple[bool, dict[str, Any]]:
    """
    使用 Redis Sliding Window 算法檢查速率限制

    原理：
    1. 使用 Redis Sorted Set (ZSET) 儲存請求時間戳
    2. Score 為毫秒級時間戳，Member 也是時間戳（保證唯一性）
    3. 每次請求時：
       - 移除窗口外的舊請求 (ZREMRANGEBYSCORE)
       - 計算當前窗口內的請求數 (ZCARD)
       - 如果未超限，添加新請求 (ZADD)
    4. 使用 Lua script 保證原子性

    Args:
        redis: Redis 客戶端（可選，如果為 None 則跳過速率限制）
        user_id: 用戶 ID
        limit: 速率限制（請求數）
        window_seconds: 時間窗口（秒）

    Returns:
        tuple[bool, dict]: (是否允許, 限制資訊)
            - allowed: True 表示允許請求，False 表示超限
            - info: {
                "limit": 限制值,
                "current": 當前窗口內請求數,
                "remaining": 剩餘可用請求數,
                "reset_at": 窗口重置時間,
                "window_seconds": 窗口大小
              }
    """
    now_ms = int(time.time() * 1000)
    reset_at = datetime.fromtimestamp(
        (now_ms + window_seconds * 1000) / 1000, tz=timezone.utc
    )

    # 如果 Redis 未啟用或不可用，跳過速率限制（允許所有請求）
    if redis is None:
        logger.debug("Redis is disabled. Rate limiting skipped for user %s", user_id)
        return True, {
            "limit": limit,
            "current": 0,
            "remaining": limit,
            "reset_at": reset_at,
            "window_seconds": window_seconds,
            "disabled": True,  # 標記 Redis 已禁用
        }

    window_start_ms = now_ms - (window_seconds * 1000)
    key = f"rate_limit:user:{user_id}"

    # Lua script 確保原子操作
    lua_script = """
    local key = KEYS[1]
    local now_ms = tonumber(ARGV[1])
    local window_start_ms = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local ttl = tonumber(ARGV[4])
    
    -- 移除窗口外的舊請求
    redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start_ms)
    
    -- 計算當前窗口內的請求數
    local current = redis.call('ZCARD', key)
    
    -- 檢查是否超限
    if current >= limit then
        return {0, current}  -- 不允許：[allowed=0, current_count]
    end
    
    -- 添加新請求（使用 now_ms 作為 member 保證唯一性）
    redis.call('ZADD', key, now_ms, now_ms)
    
    -- 設置過期時間（2 倍窗口大小，保留緩衝）
    redis.call('EXPIRE', key, ttl)
    
    return {1, current + 1}  -- 允許：[allowed=1, new_count]
    """

    try:
        # 執行 Lua script
        result = await redis.eval(
            lua_script,
            1,  # 參數個數（KEYS）
            key,  # KEYS[1]
            now_ms,  # ARGV[1]
            window_start_ms,  # ARGV[2]
            limit,  # ARGV[3]
            window_seconds * 2,  # ARGV[4] - TTL（2 倍窗口，留緩衝）
        )

        # 解析結果
        allowed_int, current_count = result[0], result[1]
        allowed = allowed_int == 1

        # 計算重置時間（當前窗口結束時間）
        reset_at = datetime.fromtimestamp(
            (now_ms + window_seconds * 1000) / 1000, tz=timezone.utc
        )

        rate_info = {
            "limit": limit,
            "current": current_count,
            "remaining": max(0, limit - current_count),
            "reset_at": reset_at,
            "window_seconds": window_seconds,
        }

        if not allowed:
            logger.warning(
                "Rate limit exceeded for user %s: %d/%d requests in %ds window",
                user_id,
                current_count,
                limit,
                window_seconds,
            )
        else:
            logger.debug(
                "Rate limit check passed for user %s: %d/%d requests",
                user_id,
                current_count,
                limit,
            )

        return allowed, rate_info

    except Exception as e:
        # Redis 錯誤時記錄日誌並允許請求（fail-open 策略）
        logger.error(
            "Redis rate limit check failed for user %s: %s. Allowing request.",
            user_id,
            str(e),
        )
        return True, {
            "limit": limit,
            "current": 0,
            "remaining": limit,
            "reset_at": datetime.fromtimestamp(
                (now_ms + window_seconds * 1000) / 1000, tz=timezone.utc
            ),
            "window_seconds": window_seconds,
            "error": str(e),
        }


async def clear_user_rate_limit(redis: Redis | None, user_id: str) -> bool:
    """
    清除用戶的速率限制記錄

    用於測試或管理員手動重置

    Args:
        redis: Redis 客戶端（可選）
        user_id: 用戶 ID

    Returns:
        bool: 是否成功刪除
    """
    if redis is None:
        logger.debug("Redis is disabled. Cannot clear rate limit for user %s", user_id)
        return False

    key = f"rate_limit:user:{user_id}"
    try:
        deleted = await redis.delete(key)
        logger.info("Cleared rate limit for user %s (deleted=%d)", user_id, deleted)
        return deleted > 0
    except Exception as e:
        logger.error("Failed to clear rate limit for user %s: %s", user_id, str(e))
        return False
