"""OpenAI tool schema builders for template-scoped guest checks."""

from __future__ import annotations

import copy
from typing import Any

from app.ai.pve_tools.schemas import ResolvedProfile


def build_run_guest_check_tool(profile: ResolvedProfile) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "run_guest_check",
            "description": (
                "在指定 VM/LXC 執行後端註冊的唯讀 guest check。"
                "指令由伺服器固定建立，不能由模型提供或覆寫。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vmid": {"type": "integer", "description": "目標 VMID"},
                    "check_key": {
                        "type": "string",
                        "enum": list(profile.keys),
                        "description": "目前模板允許的 check key",
                    },
                    "params": {
                        "type": "object",
                        "description": "check 專屬的受控參數；無參數時傳入空物件",
                    },
                },
                "required": ["vmid", "check_key", "params"],
            },
        },
    }


def build_tool_definitions(
    base_tools: list[dict[str, Any]],
    profile: ResolvedProfile | None,
) -> list[dict[str, Any]]:
    tools = copy.deepcopy(base_tools)
    if profile is not None and profile.checks:
        tools.insert(-1, build_run_guest_check_tool(profile))
    return tools
