from __future__ import annotations

from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException

from app.ai.template_recommendation.catalog_service import get_catalog
from app.infrastructure.ai.template_recommendation import client
from app.ai.template_recommendation.config import settings
from app.ai.template_recommendation.node_service import (
    build_resource_option_bundle,
    load_live_device_nodes,
)
from app.ai.template_recommendation.prompt import (
    build_chat_catalog_context,
    build_chat_system_prompt,
)
from app.ai.template_recommendation.recommendation_service import (
    extract_intent_from_chat,
    generate_ai_plan,
    normalize_ai_result,
)
from app.ai.template_recommendation.schemas import (
    ChatRequest,
    ChatResponse,
    RecommendationRequest,
)
from app.api.deps import CurrentUser


router = APIRouter(
    prefix="/ai/template-recommendation",
    tags=["ai-template-recommendation"],
)


def _strip_think_tags(text: str) -> str:
    marker = "</think>"
    idx = text.find(marker)
    if idx != -1:
        return text[idx + len(marker) :].strip()
    return text.strip()


def _apply_thinking_control(payload: dict[str, Any]) -> dict[str, Any]:
    payload["chat_template_kwargs"] = {
        **dict(payload.get("chat_template_kwargs") or {}),
        "enable_thinking": settings.vllm_enable_thinking,
    }
    return payload


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: CurrentUser) -> ChatResponse:
    del current_user
    model_name = settings.resolved_vllm_model_name
    if not model_name:
        raise HTTPException(
            status_code=503,
            detail="AI model binding is missing in config/system-ai.json.",
        )

    catalog = get_catalog()
    is_first_turn = len(request.messages) <= 1
    catalog_context = build_chat_catalog_context(
        catalog,
        request.messages,
        top_k=request.top_k,
    )
    system_prompt = build_chat_system_prompt(
        is_first_turn=is_first_turn,
        catalog_context=catalog_context,
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in request.messages:
        messages.append({"role": msg.role, "content": msg.content})

    payload = _apply_thinking_control(
        {
            "model": model_name,
            "messages": messages,
            "max_tokens": settings.vllm_chat_max_tokens,
            "temperature": settings.vllm_chat_temperature,
            "top_p": settings.vllm_top_p,
            "top_k": settings.vllm_top_k,
            "min_p": settings.vllm_min_p,
            "repetition_penalty": settings.vllm_repetition_penalty,
        }
    )

    try:
        started_at = perf_counter()
        data = await client.create_chat_completion(payload)
        elapsed_seconds = max(perf_counter() - started_at, 0.0)
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(
            usage.get("total_tokens") or (prompt_tokens + completion_tokens)
        )
        tokens_per_second = (
            completion_tokens / elapsed_seconds if elapsed_seconds > 0 else 0.0
        )

        content = _strip_think_tags(data["choices"][0]["message"]["content"] or "")

        return ChatResponse(
            reply=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            elapsed_seconds=round(elapsed_seconds, 3),
            tokens_per_second=round(tokens_per_second, 2),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI chat failed: {exc}") from exc


@router.post("/recommend", response_model=dict[str, Any])
async def recommend(request: ChatRequest, current_user: CurrentUser) -> dict[str, Any]:
    live_nodes = load_live_device_nodes()
    extracted_intent = await extract_intent_from_chat(request)
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
    del current_user

    catalog = get_catalog()
    resource_options = build_resource_option_bundle()
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
    result["live_device_nodes"] = [
        node.model_dump() for node in merged_request.device_nodes
    ]
    result["ai_metrics"] = ai_metrics
    result["resource_options"] = resource_options
    return result
