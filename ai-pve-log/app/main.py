from __future__ import annotations

from pathlib import Path
import sys

from fastapi import FastAPI

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes import router
from app.core.config import settings

app = FastAPI(
    title="Campus PVE Log — 批量系統資料分析服務",
    description=(
        "透過 PVE REST API 批量收集所有節點、VM、LXC 的系統資料。\n\n"
        "**主要端點：**\n"
        "- `GET /api/v1/snapshot` — 一次取得所有資料（批量分析入口）\n"
        "- `GET /api/v1/nodes` — 節點清單\n"
        "- `GET /api/v1/resources` — VM/LXC 摘要\n"
        "- `GET /api/v1/resource-statuses` — 即時詳細狀態\n"
        "- `GET /api/v1/resource-configs` — 設定檔\n"
        "- `GET /api/v1/storage` — 儲存空間\n"
        "- `GET /api/v1/reference` — PVE API 可取得資料說明表\n"
    ),
    version="0.1.0",
)

app.include_router(router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "proxmox_host": settings.proxmox_host,
        "fetch_config": settings.collector_fetch_config,
        "fetch_lxc_interfaces": settings.collector_fetch_lxc_interfaces,
        "max_workers": settings.collector_max_workers,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
