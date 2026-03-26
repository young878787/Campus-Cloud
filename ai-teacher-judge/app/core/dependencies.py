from __future__ import annotations

import httpx

from app.core.config import settings

# 全局 HTTP 客戶端實例（應用啟動時初始化）
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """取得全局 HTTP 客戶端實例。"""
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized. Call init_http_client() first.")
    return _http_client


async def init_http_client() -> None:
    """初始化全局 HTTP 客戶端（應用啟動時呼叫）。"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(float(settings.vllm_timeout)),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )


async def close_http_client() -> None:
    """關閉全局 HTTP 客戶端（應用關閉時呼叫）。"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
