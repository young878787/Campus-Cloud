from __future__ import annotations

from fastapi import APIRouter

from app.schemas import ExplainRequest, ExplainResponse
from app.services.ai_explainer_service import explain_analysis


router = APIRouter(tags=["explain"])


@router.post("/explain", response_model=ExplainResponse)
@router.post("/api/v1/explain", response_model=ExplainResponse)
async def explain(request: ExplainRequest):
    return await explain_analysis(request)


@router.post("/chat", response_model=ExplainResponse)
@router.post("/api/v1/chat", response_model=ExplainResponse)
async def chat(request: ExplainRequest):
    return await explain_analysis(request)
