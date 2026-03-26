from __future__ import annotations

import json
from typing import Any


def build_advisor_system_prompt() -> str:
    return """You are an expert Proxmox VE placement advisor.

Return JSON only. Do not include markdown.

The backend will validate your answer. You are making the final placement
decision only when capacity allows it.

Rules:
- Use Traditional Chinese in all user-facing text.
- Read the request, node capacities, backend traffic, audit signals, and the
  baseline rule-based plan before deciding.
- Only choose nodes that appear in node_capacities.
- The sum of machines_to_open.instance_count must not exceed request.instance_count.
- If capacity is insufficient, you may allocate fewer instances and explain why.
- Keep reasons concise and operational.

Required JSON schema:
{
  "reply": "Traditional Chinese summary",
  "effective_resource_type": "lxc|vm",
  "machines_to_open": [
    {
      "node": "node-name",
      "instance_count": 1,
      "reason": "Traditional Chinese short reason"
    }
  ],
  "reasons": ["Traditional Chinese short reason"]
}
"""


def build_advisor_user_prompt(
    *,
    request: dict[str, Any],
    rule_based_plan: dict[str, Any],
    backend_traffic: dict[str, Any] | None,
    audit_signals: dict[str, Any] | None,
    node_capacities: list[dict[str, Any]],
) -> str:
    context = {
        "request": request,
        "rule_based_plan": rule_based_plan,
        "backend_traffic": backend_traffic,
        "audit_signals": audit_signals,
        "node_capacities": node_capacities,
    }
    return (
        "Decide the final Proxmox VE placement.\n"
        "If the AI decision is not safe or not valid, the backend will fall back "
        "to the rule-based plan.\n"
        "Return JSON only.\n\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )
