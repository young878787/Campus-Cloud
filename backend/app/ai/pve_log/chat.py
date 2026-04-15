from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.ai.pve_log.collector import collect_snapshot
from app.ai.pve_log.config import settings
from app.ai.pve_log.schemas import ChatResponse, ToolCallRecord

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是 Campus Cloud PVE 管理助手，專門協助管理員查詢 Proxmox VE 虛擬化平台的資源狀態。

工具使用原則：
- 問題只涉及一種資源時，優先呼叫最精確的工具（例如只查儲存空間就用 get_storage，不要呼叫 get_resources）。
- 需要特定 VM/LXC 詳情時才呼叫 get_resource_detail，並傳入正確的 vmid。
- 若問題同時涉及多類資料，可以在同一輪呼叫多個工具。

回覆格式：
- 使用繁體中文，語氣清楚、簡潔。
- 請用 Markdown 格式輸出，優先使用標題、條列、粗體來整理內容。
- 數字單位換算為人類可讀格式：bytes -> GB / MB、比例 -> %（保留一位小數）。
- 若問題與 PVE 無關，說明你只處理 PVE 相關查詢。"""

_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_resources",
            "description": "取得所有 VM 與 LXC 容器的摘要清單。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {"type": "string"},
                    "resource_type": {"type": "string", "enum": ["qemu", "lxc"]},
                    "status": {"type": "string", "enum": ["running", "stopped"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nodes",
            "description": "取得所有 PVE 節點的清單。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_storage",
            "description": "取得所有儲存空間資訊。",
            "parameters": {
                "type": "object",
                "properties": {"node": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_resource_detail",
            "description": "取得指定 vmid 的完整詳細資訊。",
            "parameters": {
                "type": "object",
                "properties": {"vmid": {"type": "integer"}},
                "required": ["vmid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cluster",
            "description": "取得叢集整體概覽。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _execute_tool_sync(snapshot, name: str, args: dict) -> Any:
    if name == "get_nodes":
        return [n.model_dump(mode="json") for n in snapshot.nodes]

    if name == "get_storage":
        result = snapshot.storages
        if args.get("node"):
            result = [s for s in result if s.node == args["node"]]
        return [s.model_dump(mode="json") for s in result]

    if name == "get_resources":
        result = snapshot.resources
        if args.get("node"):
            result = [r for r in result if r.node == args["node"]]
        if args.get("resource_type"):
            result = [r for r in result if r.resource_type == args["resource_type"]]
        if args.get("status"):
            result = [r for r in result if r.status == args["status"]]
        return [r.model_dump(mode="json") for r in result]

    if name == "get_resource_detail":
        vmid = int(args["vmid"])
        summary = next((r for r in snapshot.resources if r.vmid == vmid), None)
        if summary is None:
            return {"error": f"找不到 vmid={vmid}"}

        status_detail = next((s for s in snapshot.resource_statuses if s.vmid == vmid), None)
        config = next((c for c in snapshot.resource_configs if c.vmid == vmid), None)
        interfaces = [i for i in snapshot.network_interfaces if i.vmid == vmid]

        return {
            "summary": summary.model_dump(mode="json"),
            "status": status_detail.model_dump(mode="json") if status_detail else None,
            "config": config.model_dump(mode="json", exclude={"raw"}) if config else None,
            "network_interfaces": [i.model_dump(mode="json") for i in interfaces],
        }

    if name == "get_cluster":
        return snapshot.cluster.model_dump(mode="json")

    return {"error": f"未知工具：{name}"}


async def chat(message: str) -> ChatResponse:
    if not settings.vllm_base_url or not settings.vllm_model_name:
        return ChatResponse(
            reply="",
            error="vLLM 設定不完整，請確認 .env 中的 TEMPLATE_RECOMMENDATION_VLLM_* 設定",
        )

    url = f"{settings.vllm_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.vllm_api_key}",
        "Content-Type": "application/json",
    }

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    tools_called: list[ToolCallRecord] = []

    async with httpx.AsyncClient(timeout=settings.chat_timeout) as client:
        payload: dict[str, Any] = {
            "model": settings.vllm_model_name,
            "messages": messages,
            "tools": _TOOLS,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except Exception:
            logger.exception("vLLM 請求失敗")
            return ChatResponse(reply="", error="無法連線至 LLM 服務")

        try:
            data = resp.json()
        except Exception as exc:
            logger.error("vLLM 第一次回應解析失敗：%s", exc)
            return ChatResponse(reply="", error="LLM 回應格式錯誤（非 JSON）")

        choices = data.get("choices") or []
        if not choices:
            return ChatResponse(reply="", error="LLM 回傳空回應（choices 為空）")

        assistant_msg = choices[0].get("message") or {}
        messages.append(assistant_msg)

        tool_calls = assistant_msg.get("tool_calls") or []

        if tool_calls:
            try:
                snapshot = await asyncio.to_thread(collect_snapshot)
            except Exception as exc:
                logger.error("收集 PVE 快照失敗：%s", exc)
                return ChatResponse(reply="", error=f"收集 PVE 資料失敗：{exc}")

            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args: dict = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    func_args = {}

                tools_called.append(ToolCallRecord(name=func_name, args=func_args))

                try:
                    result = _execute_tool_sync(snapshot, func_name, func_args)
                    tool_content = json.dumps(result, ensure_ascii=False, default=str)
                except Exception as exc:
                    logger.error("工具 %s 執行失敗：%s", func_name, exc)
                    tool_content = json.dumps({"error": str(exc)}, ensure_ascii=False)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_content,
                    }
                )

            payload2: dict[str, Any] = {
                "model": settings.vllm_model_name,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 4096,
            }
            try:
                resp2 = await client.post(url, json=payload2, headers=headers)
                resp2.raise_for_status()
                data2 = resp2.json()
            except Exception as exc:
                logger.error("vLLM 第二次請求失敗：%s", exc)
                return ChatResponse(reply="", tools_called=tools_called, error=f"取得最終回答失敗：{exc}")

            choices2 = data2.get("choices") or []
            reply = ((choices2[0].get("message") or {}).get("content") or "") if choices2 else ""
            return ChatResponse(reply=reply, tools_called=tools_called)

        reply = assistant_msg.get("content") or ""
        return ChatResponse(reply=reply, tools_called=tools_called)
