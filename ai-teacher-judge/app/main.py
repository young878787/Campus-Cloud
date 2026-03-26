from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.routes.rubric import router as rubric_router
from app.core.config import settings
from app.core.dependencies import init_http_client, close_http_client
from app.core.logging_config import setup_logging


# 初始化日誌
setup_logging(level="INFO")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用啟動和關閉時的生命週期管理。"""
    # 啟動：初始化 HTTP 客戶端連線池
    logger.info("Initializing HTTP client pool...")
    await init_http_client()
    logger.info(f"Application started successfully on {settings.host}:{settings.port}")
    yield
    # 關閉：清理資源
    logger.info("Shutting down application...")
    await close_http_client()
    logger.info("Application shutdown complete")


# 速率限制器
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Campus Rubric Assistant",
    description="AI-driven grading rubric analysis and refinement for teachers.",
    lifespan=lifespan,
)

# 註冊速率限制器
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 配置
if settings.cors_origins:
    origins = [origin.strip() for origin in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(rubric_router)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
@app.get(f"{settings.api_v1_str}/health")
def health() -> dict:
    return {
        "status": "ok",
        "vllm_configured": bool(settings.vllm_model_name),
    }


@app.get("/ui-config")
def ui_config() -> dict:
    return {
        "api_base_url": settings.frontend_api_base_url.rstrip("/"),
    }
