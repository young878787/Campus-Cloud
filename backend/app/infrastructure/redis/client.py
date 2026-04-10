from __future__ import annotations

import logging
from typing import Any

try:
    from redis.asyncio import ConnectionPool, Redis
except ModuleNotFoundError:  # pragma: no cover - depends on local env
    ConnectionPool = Any  # type: ignore[assignment]
    Redis = Any  # type: ignore[assignment]

from app.features.ai.config import settings

logger = logging.getLogger(__name__)

_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None
_redis_backend_available = ConnectionPool is not Any
_redis_enabled: bool = settings.redis_enabled and _redis_backend_available


async def init_redis() -> None:
    global _redis_pool, _redis_client

    if not _redis_backend_available:
        logger.warning(
            "Redis Python package is not installed. Rate limiting functionality will be skipped."
        )
        return

    if not _redis_enabled:
        logger.info(
            "Redis is disabled (REDIS_ENABLED=false). "
            "Rate limiting functionality will be skipped."
        )
        return

    try:
        _redis_pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
        _redis_client = Redis(connection_pool=_redis_pool)
        await _redis_client.ping()
        logger.info("Redis connected successfully: %s", settings.redis_url)
    except Exception as exc:
        logger.error(
            "Failed to connect to Redis: %s. "
            "Rate limiting will be disabled. "
            "To suppress this error, set REDIS_ENABLED=false in .env",
            exc,
        )
        _redis_client = None
        if _redis_pool:
            await _redis_pool.aclose()
            _redis_pool = None


async def get_redis() -> Redis | None:
    if not _redis_enabled:
        return None

    if _redis_client is None:
        logger.warning("Redis not initialized, attempting to initialize now...")
        await init_redis()

    return _redis_client


async def close_redis() -> None:
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
    return _redis_enabled


def is_redis_available() -> bool:
    return _redis_enabled and _redis_client is not None
