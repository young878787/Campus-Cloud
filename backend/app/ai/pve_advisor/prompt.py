from __future__ import annotations

import json
from typing import Any


def build_advisor_system_prompt() -> str:
    return """# Role
You are an expert PVE placement advisor for a campus cloud platform.

# Task
Explain node placement recommendations for VM or LXC requests using the provided cluster state and placement analysis.

# Rules
- Reply entirely in Traditional Chinese (zh-TW).
- Be concise, practical, and operational.
- Start with the recommended node or the main constraint first.
- Use the provided placement result as the source of truth. Do not invent node capacity or template availability.
- If the request cannot be fully placed, clearly state the blocking factor.
- Mention important operational signals when they matter, such as pending backend requests or recent audit-log burst.
- Make it explicit that this response is only a recommendation and has not executed provisioning or power actions.
- Do not output JSON.
- Do not reveal chain-of-thought or internal reasoning.
"""


def build_advisor_user_prompt(
    *,
    request: dict[str, Any],
    placement: dict[str, Any],
    backend_traffic: dict[str, Any] | None,
    audit_signals: dict[str, Any] | None,
    node_capacities: list[dict[str, Any]],
) -> str:
    compact_context = {
        "request": request,
        "placement": placement,
        "backend_traffic": backend_traffic,
        "audit_signals": audit_signals,
        "node_capacities": node_capacities,
    }
    return (
        "請根據以下 PVE placement 分析資料，產生給使用者看的最終建議文字。\n\n"
        f"{json.dumps(compact_context, ensure_ascii=False)}"
    )
