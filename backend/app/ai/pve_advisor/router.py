from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.ai.pve_advisor.config import settings
from app.ai.pve_advisor.recommendation_service import generate_recommendation
from app.ai.pve_advisor.schemas import PlacementAdvisorResponse, PlacementRequest
from app.api.deps import SessionDep

router = APIRouter(
    prefix="/ai/pve-advisor",
    tags=["ai-pve-advisor"],
)


@router.post("/recommend", response_model=PlacementAdvisorResponse)
async def recommend_placement(
    request: PlacementRequest,
    session: SessionDep,
) -> PlacementAdvisorResponse:
    if not settings.enabled:
        raise HTTPException(status_code=503, detail="PVE advisor is disabled.")
    return await generate_recommendation(session=session, request=request)
