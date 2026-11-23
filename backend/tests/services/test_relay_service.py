"""app/services/llm_gateway/relay_service.py 的上游錯誤處理：上游回傳錯誤 body 時只回通用訊息，不外流內部別名與位址。"""

from __future__ import annotations

# ── 5. 上游錯誤 body 不外流 ─────────────────────────────────────────────────


def test_upstream_error_body_is_replaced_with_a_generic_message() -> None:
    import json

    import httpx
    from fastapi import Request

    from app.services.llm_gateway import relay_service

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/ai-proxy/chat/completions",
            "headers": [],
            "query_string": b"",
        }
    )
    upstream = httpx.Response(400, text="internal alias qwen-prod @ http://10.0.0.5:4000")
    response = relay_service.upstream_failure(
        request=request,
        upstream=upstream,
        body=upstream.content,
        context="relay:chat/completions",
    )
    assert response.status_code == 400
    payload = json.loads(bytes(response.body))
    assert "10.0.0.5" not in payload["error"]["message"]
    assert payload["error"]["code"] == "upstream_error"
