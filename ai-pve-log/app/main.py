from __future__ import annotations

from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes import router
from app.core.config import settings

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Campus PVE Log — 批量系統資料分析服務",
    description=(
        "透過 PVE REST API 批量收集所有節點、VM、LXC 的系統資料，"
        "並提供 AI 自然語言查詢介面（Tool Calling）。\n\n"
        "**主要端點：**\n"
        "- `POST /api/v1/chat` — AI 自然語言查詢（Tool Calling）\n"
        "- `GET /api/v1/snapshot` — 一次取得所有資料（批量分析入口）\n"
        "- `GET /api/v1/nodes` — 節點清單\n"
        "- `GET /api/v1/resources` — VM/LXC 摘要\n"
        "- `GET /api/v1/resource-statuses` — 即時詳細狀態\n"
        "- `GET /api/v1/resource-configs` — 設定檔\n"
        "- `GET /api/v1/storage` — 儲存空間\n"
        "- `GET /api/v1/reference` — PVE API 可取得資料說明表\n\n"
        "**測試前端：** [`/`](/) "
    ),
    version="0.2.0",
)

app.include_router(router)

# 靜態檔案（測試前端）
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def frontend():
    """提供測試前端 HTML"""
    html_file = _STATIC_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<p>找不到 static/index.html</p>", status_code=404)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "proxmox_host": settings.proxmox_host,
        "fetch_config": settings.collector_fetch_config,
        "fetch_lxc_interfaces": settings.collector_fetch_lxc_interfaces,
        "max_workers": settings.collector_max_workers,
        "vllm_base_url": settings.vllm_base_url,
        "vllm_model": settings.vllm_model_name or "(未設定)",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
