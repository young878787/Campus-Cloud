from __future__ import annotations

from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.analytics import router as analytics_router
from app.api.routes.explain import router as explain_router
from app.api.routes.sources import router as sources_router
from app.core.config import settings


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(
    title="Campus PVE Placement Advisor",
    description="Standalone service for PVE node capacity visibility and AI-assisted workload placement.",
)

app.include_router(analytics_router)
app.include_router(explain_router)
app.include_router(sources_router, prefix=settings.api_v1_str)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
@app.get(f"{settings.api_v1_str}/health")
def health() -> dict:
    return {
        "status": "ok",
        "use_direct_proxmox": settings.use_direct_proxmox,
        "ai_configured": bool(settings.vllm_model_name),
        "aggregation_stair_coefficient": settings.aggregation_stair_coefficient,
        "placement_headroom_ratio": settings.placement_headroom_ratio,
        "gpu_map_count": len(settings.parsed_backend_node_gpu_map),
        "node_snapshot_count": len(settings.parsed_nodes_snapshot),
        "token_snapshot_count": len(settings.parsed_token_usage_snapshots),
        "gpu_snapshot_count": len(settings.parsed_gpu_metric_snapshots),
    }


@app.get("/ui-config")
def ui_config() -> dict:
    api_base_url = settings.frontend_api_base_url.rstrip("/")
    ai_configured = bool(settings.vllm_model_name)
    return {
        "api_base_url": api_base_url,
        "api_v1_str": settings.api_v1_str,
        "ai_configured": ai_configured,
        "apiBaseUrl": api_base_url,
        "apiV1Str": settings.api_v1_str,
        "aiConfigured": ai_configured,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
