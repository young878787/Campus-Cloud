import sentry_sdk
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.websocket import vnc_proxy
from app.api.websocket.terminal import terminal_proxy
from app.core.config import settings
from app.core.redis import close_redis, init_redis
from app.exceptions import AppError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # Startup: 初始化 Redis
    await init_redis()
    yield
    # Shutdown: 關閉 Redis
    await close_redis()


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=str(settings.SENTRY_DSN), traces_sample_rate=1.0, send_default_pii=False
    )

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.websocket("/ws/vnc/{vmid}")
async def websocket_vnc_proxy(websocket: WebSocket, vmid: int, token: str = ""):
    await vnc_proxy(websocket, vmid, token=token)


@app.websocket("/ws/terminal/{vmid}")
async def websocket_terminal_proxy(websocket: WebSocket, vmid: int, token: str = ""):
    await terminal_proxy(websocket, vmid, token=token)
