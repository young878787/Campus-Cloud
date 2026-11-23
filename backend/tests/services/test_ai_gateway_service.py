"""app/services/llm_gateway/ai_gateway_service.py 產生使用者 API 金鑰時，前綴須採用較長的 API_KEY_PREFIX_LENGTH。"""

from __future__ import annotations

from app.models import API_KEY_PREFIX_LENGTH
from app.services.llm_gateway import ai_gateway_service

# ── 6. 前綴長度與碰撞 ───────────────────────────────────────────────────────


def test_generated_prefix_uses_the_longer_length() -> None:
    api_key = ai_gateway_service._generate_user_api_key()
    prefix = ai_gateway_service._credential_prefix(api_key)
    assert api_key.startswith("ccai_")
    assert len(prefix) == API_KEY_PREFIX_LENGTH
