"""
Redis 連接管理模組

提供全局 Redis 連接池和客戶端管理
支援可選的 Redis 監控功能（透過 REDIS_ENABLED 環境變數控制）
"""

import logging

from redis.asyncio import ConnectionPool, Redis

from app.ai_api.config import settings

logger = logging.getLogger(__name__)

# 全局連接池和客戶端
_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None
_redis_enabled: bool = settings.redis_enabled


async def init_redis() -> None:
    """
    初始化 Redis 連接池

    在應用啟動時調用
    如果 REDIS_ENABLED=false，則跳過初始化（不會報錯）
    """
    global _redis_pool, _redis_client

    if not _redis_enabled:
        logger.info(
            "Redis is disabled (REDIS_ENABLED=false). "
            "Rate limiting functionality will be skipped."
        )
        return

    try:
        _redis_pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,  # 自動解碼為字串
            max_connections=50,  # 最大連接數
            socket_connect_timeout=5,  # 連接超時 5 秒
            socket_keepalive=True,  # 保持連接活躍
        )
        _redis_client = Redis(connection_pool=_redis_pool)

        # 測試連接
        await _redis_client.ping()
        logger.info("✅ Redis connected successfully: %s", settings.redis_url)

    except Exception as e:
        logger.error(
            "❌ Failed to connect to Redis: %s. "
            "Rate limiting will be disabled. "
            "To suppress this error, set REDIS_ENABLED=false in .env",
            e,
        )
        # 清理失敗的客戶端
        _redis_client = None
        if _redis_pool:
            await _redis_pool.aclose()
            _redis_pool = None


async def get_redis() -> Redis | None:
    """
    獲取 Redis 客戶端

    Returns:
        Redis | None: 異步 Redis 客戶端實例，如果 Redis 未啟用或連接失敗則返回 None

    Note:
        調用方應該檢查返回值是否為 None，並相應地處理
    """
    if not _redis_enabled:
        return None

    if _redis_client is None:
        logger.warning("Redis not initialized, attempting to initialize now...")
        await init_redis()

    return _redis_client


async def close_redis() -> None:
    """
    關閉 Redis 連接

    在應用關閉時調用
    """
    global _redis_client, _redis_pool

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis client closed")

    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("Redis connection pool closed")


def is_redis_enabled() -> bool:
    """
    檢查 Redis 是否啟用

    Returns:
        bool: True 如果 Redis 已啟用，否則 False
    """
    return _redis_enabled


def is_redis_available() -> bool:
    """
    檢查 Redis 是否可用（已啟用且連接成功）

    Returns:
        bool: True 如果 Redis 已連接且可用，否則 False
    """
    return _redis_enabled and _redis_client is not None
