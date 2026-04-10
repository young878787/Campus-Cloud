from __future__ import annotations

from typing import Any

import httpx

from app.ai.template_recommendation.config import settings


class TemplateRecommendationClient:
    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {settings.vllm_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=settings.vllm_timeout) as http_client:
            response = await http_client.post(
                f"{settings.vllm_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()


client = TemplateRecommendationClient()
