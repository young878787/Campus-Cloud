from __future__ import annotations

import json

import httpx

from app.core.config import settings
from app.schemas import AnalysisResponse, ExplainRequest, ExplainResponse
from app.services.analytics_service import build_analysis


async def explain_analysis(request: ExplainRequest) -> ExplainResponse:
    analysis = await build_analysis(limit_audit_logs=request.limit_audit_logs)
    question = (
        request.question.strip()
        if request.question and request.question.strip()
        else "請根據目前分析結果說明系統狀態、風險與優先處理順序。"
    )

    if not settings.vllm_model_name:
        return ExplainResponse(
            answer=_build_fallback_answer(analysis, question),
            ai_used=False,
            analysis=analysis,
            warning="VLLM_MODEL_NAME 未設定，已使用規則式解釋。",
        )

    try:
        answer = await _call_vllm(analysis=analysis, request=request, question=question)
        return ExplainResponse(
            answer=answer,
            ai_used=True,
            model=settings.vllm_model_name,
            analysis=analysis,
        )
    except Exception as exc:
        return ExplainResponse(
            answer=_build_fallback_answer(analysis, question),
            ai_used=False,
            analysis=analysis,
            warning=f"AI 解釋暫時不可用，已改用規則式解釋: {exc}",
        )


async def _call_vllm(
    *,
    analysis: AnalysisResponse,
    request: ExplainRequest,
    question: str,
) -> str:
    system_prompt = (
        "你是一個校園雲端平台的 AI Log Analytics 助理。"
        "你的任務是根據監控、審計、事件與建議資料，"
        "用台灣繁體中文提供清楚、可執行、可解釋的分析。"
        "不要編造不存在的事件。"
        "若資料來源缺漏，要明確指出。"
        "回答請分成短段落，必要時才用條列。"
    )

    compact_context = {
        "summary": analysis.summary,
        "aggregation": analysis.aggregation.model_dump(),
        "events": [item.model_dump() for item in analysis.events],
        "recommendations": [item.model_dump() for item in analysis.recommendations],
        "source_health": [item.model_dump() for item in analysis.source_health],
    }
    messages = [{"role": "system", "content": system_prompt}]
    for item in request.history[-8:]:
        messages.append({"role": item.role, "content": item.content})
    messages.append(
        {
            "role": "user",
            "content": (
                f"問題: {question}\n\n"
                f"分析上下文: {json.dumps(compact_context, ensure_ascii=False)}"
            ),
        }
    )

    payload = {
        "model": settings.vllm_model_name,
        "messages": messages,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }
    headers = {
        "Authorization": f"Bearer {settings.vllm_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=settings.vllm_timeout) as client:
        response = await client.post(
            f"{_normalized_vllm_base_url()}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
    return str(data["choices"][0]["message"]["content"]).strip()


def _normalized_vllm_base_url() -> str:
    base_url = settings.vllm_base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def _build_fallback_answer(analysis: AnalysisResponse, question: str) -> str:
    top_events = analysis.events[:3]
    top_recommendations = analysis.recommendations[:3]
    lines = [
        f"問題焦點: {question}",
        "",
        f"目前摘要: {analysis.summary}",
    ]

    if top_events:
        lines.append("")
        lines.append("重點事件:")
        for item in top_events:
            lines.append(f"- [{item.severity}] {item.summary}")

    if top_recommendations:
        lines.append("")
        lines.append("優先建議:")
        for item in top_recommendations:
            lines.append(f"- {item.action} 理由: {item.reason}")

    missing_sources = [item.name for item in analysis.source_health if not item.available]
    if missing_sources:
        lines.append("")
        lines.append(
            "資料缺口:"
            f" 目前以下來源不可用: {', '.join(missing_sources)}。"
            " 解釋結果會受到資料完整度限制。"
        )

    return "\n".join(lines)
