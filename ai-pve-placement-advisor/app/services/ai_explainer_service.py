from __future__ import annotations

import json

import httpx

from app.core.config import settings
from app.schemas import AnalysisResponse, ExplainRequest, ExplainResponse
from app.services.analytics_service import build_analysis


async def explain_analysis(request: ExplainRequest) -> ExplainResponse:
    analysis = await build_analysis(placement_request=request.placement_request)
    question = (
        request.question.strip()
        if request.question and request.question.strip()
        else "請根據目前配置結果，說明建議如何分配與主要原因。"
    )

    if not settings.vllm_model_name:
        return ExplainResponse(
            answer=_build_fallback_answer(analysis),
            ai_used=False,
            analysis=analysis,
            warning="VLLM_MODEL_NAME is not configured, so the service returned a rule-based answer.",
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
            answer=_build_fallback_answer(analysis),
            ai_used=False,
            analysis=analysis,
            warning=f"AI call failed, so the service returned a rule-based answer: {exc}",
        )


async def _call_vllm(
    *,
    analysis: AnalysisResponse,
    request: ExplainRequest,
    question: str,
) -> str:
    system_prompt = (
        "你是 PVE 資源配置助理。"
        "請只用繁體中文回答。"
        "請根據目前節點容量、Guest 壓力、使用者壓力與 placement 結果，"
        "直接說明建議如何分配，以及這樣分配的原因。"
        "不要輸出事件列表、前言、結語或其他多餘內容。"
    )

    compact_context = {
        "question": question,
        "summary": analysis.summary,
        "placement": analysis.placement.model_dump() if analysis.placement else None,
        "node_capacities": [item.model_dump() for item in analysis.node_capacities],
        "recommendations": [item.model_dump() for item in analysis.recommendations],
    }
    messages = [{"role": "system", "content": system_prompt}]
    for item in request.history[-8:]:
        messages.append({"role": item.role, "content": item.content})
    messages.append(
        {
            "role": "user",
            "content": (
                f"問題：{question}\n\n"
                f"分析資料：{json.dumps(compact_context, ensure_ascii=False)}"
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


def _build_fallback_answer(analysis: AnalysisResponse) -> str:
    if analysis.placement is None:
        return f"目前尚未提供 placement 請求。{analysis.summary}"

    placement_lines = [
        f"{item.node} 放 {item.instance_count} 台" for item in analysis.placement.placements
    ]
    placement_text = "、".join(placement_lines) if placement_lines else "目前沒有可安全放置的節點"

    reason_lines = []
    if analysis.placement.request.estimated_users_per_instance > 0:
        reason_lines.append(
            f"每台預估 {analysis.placement.request.estimated_users_per_instance} 人同時使用，"
            f"因此用每台 {analysis.placement.effective_cpu_cores_per_instance:.1f} CPU、"
            f"{analysis.placement.effective_memory_bytes_per_instance / (1024 ** 3):.1f} GiB 記憶體做安全規劃"
        )

    for item in analysis.placement.placements:
        reason_lines.append(
            f"{item.node} 分配後仍保留 {item.remaining_cpu_cores:.1f} CPU、"
            f"{item.remaining_memory_bytes / (1024 ** 3):.1f} GiB 記憶體、"
            f"{item.remaining_disk_bytes / (1024 ** 3):.1f} GiB 磁碟"
        )

    if analysis.placement.unassigned_instances > 0:
        reason_lines.append(
            f"仍有 {analysis.placement.unassigned_instances} 台因安全餘裕不足而無法配置"
        )

    reasons = "；".join(reason_lines) if reason_lines else analysis.summary
    return f"建議分配：{placement_text}。原因：{reasons}。"
