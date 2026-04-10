from __future__ import annotations

from fastapi import APIRouter

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
    return await generate_recommendation(session=session, request=request)


__all__ = ["generate_recommendation", "recommend_placement", "router", "settings"]
