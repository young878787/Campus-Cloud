from fastapi import APIRouter

from app.api.routes import (
    ai_api,
    ai_monitoring,
    ai_proxy,
    ai_pve_log,
    ai_template_recommendation,
)

# Unified AI router mount point for core AI-related APIs.
# Keep pve-advisor separate for now per integration plan.
router = APIRouter()
router.include_router(ai_api.router)
router.include_router(ai_monitoring.router)
router.include_router(ai_proxy.router)
router.include_router(ai_pve_log.router)
router.include_router(ai_template_recommendation.router)
