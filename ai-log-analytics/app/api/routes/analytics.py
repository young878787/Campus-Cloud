from __future__ import annotations

from fastapi import APIRouter

from app.schemas import AnalysisResponse
from app.services.analytics_service import build_analysis


router = APIRouter(tags=["analytics"])


@router.get("/analyze", response_model=AnalysisResponse)
@router.get("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze(limit_audit_logs: int = 200):
    return await build_analysis(limit_audit_logs=limit_audit_logs)
