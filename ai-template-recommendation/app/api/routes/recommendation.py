from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from app.main_state import catalog
from app.schemas.recommendation import ChatRequest, ChatResponse, RecommendationRequest
from app.services.backend_nodes_service import fetch_backend_node_payload, normalize_node_payload
from app.services.recommendation_service import (
    generate_ai_plan,
    generate_chat_reply,
    extract_intent_from_chat,
    normalize_ai_result,
)
from app.services.resource_options_service import fetch_resource_options


router = APIRouter(tags=["recommendation"])


@router.post("/chat", response_model=ChatResponse)
@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    return await generate_chat_reply(request)


@router.post("/recommend")
@router.post("/api/v1/recommend")
async def recommend(request: ChatRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    payload, resource_options, extracted_intent = await asyncio.gather(
        fetch_backend_node_payload(auth_header),
        fetch_resource_options(auth_header),
        extract_intent_from_chat(request),
    )
    live_nodes = normalize_node_payload(payload)
    
    merged_request = RecommendationRequest(
        goal=extracted_intent.goal_summary,
        role=extracted_intent.role,
        course_context=extracted_intent.course_context,
        budget_mode=extracted_intent.budget_mode,
        needs_public_web=extracted_intent.needs_public_web,
        needs_database=extracted_intent.needs_database,
        requires_gpu=extracted_intent.requires_gpu,
        needs_windows=extracted_intent.needs_windows,
        device_nodes=live_nodes or request.device_nodes,
        top_k=request.top_k,
    )

    ai_result, ai_metrics = await generate_ai_plan(
        merged_request,
        merged_request.device_nodes,
        catalog,
        request.messages,
        resource_options=resource_options,
    )
    result = normalize_ai_result(
        ai_result,
        merged_request,
        merged_request.device_nodes,
        catalog,
        resource_options=resource_options,
    )
    result["live_device_nodes"] = [node.model_dump() for node in merged_request.device_nodes]
    result["ai_metrics"] = ai_metrics
    result["resource_options"] = resource_options
    return result

