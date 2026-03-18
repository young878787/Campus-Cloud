from __future__ import annotations

from fastapi import APIRouter

from app.schemas import AnalysisResponse, PlacementRequest
from app.services.analytics_service import build_analysis


router = APIRouter(tags=["analytics"])


@router.get("/analyze", response_model=AnalysisResponse)
@router.get("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze():
    return await build_analysis()


@router.post("/placement/recommend", response_model=AnalysisResponse)
@router.post("/api/v1/placement/recommend", response_model=AnalysisResponse)
async def recommend_placement(request: PlacementRequest):
    return await build_analysis(placement_request=request)
