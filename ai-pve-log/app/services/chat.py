"""AI 對話服務 — 基於 Qwen3 Tool Calling

流程：
  1. 帶著工具定義向 vLLM 發出第一次請求
  2. 若 AI 回傳 tool_calls，逐一執行（內部呼叫 collector，不走 HTTP）
  3. 將工具結果加回 messages，發出第二次請求取得最終回答
  4. 回傳 ChatResponse

設計重點：
  - 一次 chat 請求只收集一次 PVE 快照（lazy + cached），
    多個 tool_calls 共用同一份快照，兼顧效率與一致性。
  - 工具直接呼叫 collector 函式，不走 HTTP，無額外開銷。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.chat import ChatResponse, ToolCallRecord
from app.services.collector import collect_snapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 系統提示詞
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是 Campus Cloud PVE 管理助手，專門協助管理員查詢 Proxmox VE 虛擬化平台的資源狀態。

工具使用原則：
- 問題只涉及一種資源時，優先呼叫最精確的工具（例如只查儲存空間就用 get_storage，不要呼叫 get_resources）。
- 需要特定 VM/LXC 詳情時才呼叫 get_resource_detail，並傳入正確的 vmid。
- 若問題同時涉及多類資料，可以在同一輪呼叫多個工具。

回覆格式：
- 使用繁體中文，語氣清楚、簡潔。
- 請用 Markdown 格式輸出，優先使用標題、條列、粗體來整理內容。
- 數字單位換算為人類可讀格式：bytes → GB / MB、比例 → %（保留一位小數）。
- 若適合，允許使用 Markdown 表格，但不要為了湊版面而硬塞表格。
- 若問題與 PVE 無關，說明你只處理 PVE 相關查詢。\
"""

# ---------------------------------------------------------------------------
# Tool 定義（OpenAI function-calling 格式）
# ---------------------------------------------------------------------------

_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_resources",
            "description": (
                "取得所有 VM 與 LXC 容器的摘要清單。"
                "可依節點名稱、資源類型（qemu/lxc）、狀態（running/stopped）篩選。"
                "回傳：vmid、名稱、類型、節點、狀態、CPU/記憶體/磁碟使用率等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "string",
                        "description": "篩選特定節點名稱（可選，不填則回傳所有節點）",
                    },
                    "resource_type": {
                        "type": "string",
                        "enum": ["qemu", "lxc"],
                        "description": "篩選資源類型：qemu（VM）或 lxc（容器）（可選）",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["running", "stopped"],
                        "description": "篩選狀態（可選）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nodes",
            "description": (
                "取得所有 PVE 節點的清單，包含每個節點的"
                "CPU 使用率、核心數、記憶體使用量、磁碟使用量、開機時間。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_storage",
            "description": (
                "取得所有儲存空間資訊，包含容量、已用空間、使用率、類型。可依節點篩選。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "string",
                        "description": "篩選特定節點的儲存空間（可選）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_resource_detail",
            "description": (
                "取得指定 vmid 的完整詳細資訊，包含："
                "摘要、即時狀態（CPU/記憶體/磁碟讀寫/網路流量）、"
                "設定檔（CPU 核心數、記憶體大小、磁碟大小、是否開機自啟）、"
                "LXC 網路介面（IP 位址）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vmid": {
                        "type": "integer",
                        "description": "VM 或 LXC 的 ID",
                    },
                },
                "required": ["vmid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cluster",
            "description": "取得叢集整體概覽：叢集名稱、是否為多節點叢集、節點數、quorum 狀態。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ---------------------------------------------------------------------------
# Tool 執行器
# ---------------------------------------------------------------------------


def _execute_tool_sync(snapshot, name: str, args: dict) -> Any:
    """使用已收集好的 snapshot 執行工具，同步版本（供 asyncio.to_thread 包裝）。"""
    if name == "get_nodes":
        return [n.model_dump(mode="json") for n in snapshot.nodes]

    elif name == "get_storage":
        result = snapshot.storages
        if args.get("node"):
            result = [s for s in result if s.node == args["node"]]
        return [s.model_dump(mode="json") for s in result]

    elif name == "get_resources":
        result = snapshot.resources
        if args.get("node"):
            result = [r for r in result if r.node == args["node"]]
        if args.get("resource_type"):
            result = [r for r in result if r.resource_type == args["resource_type"]]
        if args.get("status"):
            result = [r for r in result if r.status == args["status"]]
        return [r.model_dump(mode="json") for r in result]

    elif name == "get_resource_detail":
        vmid = int(args["vmid"])
        summary = next((r for r in snapshot.resources if r.vmid == vmid), None)
        if summary is None:
            return {"error": f"找不到 vmid={vmid}"}
        status_detail = next(
            (s for s in snapshot.resource_statuses if s.vmid == vmid), None
        )
        config = next((c for c in snapshot.resource_configs if c.vmid == vmid), None)
        interfaces = [i for i in snapshot.network_interfaces if i.vmid == vmid]
        return {
            "summary": summary.model_dump(mode="json"),
            "status": status_detail.model_dump(mode="json") if status_detail else None,
            # raw 欄位含完整 Proxmox 原始設定，資訊冗餘且大量消耗 LLM context，予以排除
            "config": config.model_dump(mode="json", exclude={"raw"})
            if config
            else None,
            "network_interfaces": [i.model_dump(mode="json") for i in interfaces],
        }

    elif name == "get_cluster":
        return snapshot.cluster.model_dump(mode="json")

    else:
        return {"error": f"未知工具：{name}"}


# ---------------------------------------------------------------------------
# 主對話函式
# ---------------------------------------------------------------------------


async def chat(message: str) -> ChatResponse:
    """單次 AI 對話，支援 Tool Calling。

    設計：
    - 第一次 LLM 請求帶工具定義
    - 若 AI 呼叫工具，收集快照（僅一次），執行所有工具
    - 第二次 LLM 請求取得最終回答
    """
    if not settings.vllm_base_url or not settings.vllm_model_name:
        return ChatResponse(
            reply="",
            error="vLLM 設定不完整，請確認 .env 中的 VLLM_* 設定",
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
    _snapshot = None  # lazy，只有工具真的被呼叫時才收集

    async with httpx.AsyncClient(timeout=settings.chat_timeout) as client:
        # ── 第一次請求：帶工具定義 ──────────────────────────────────────
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
        except httpx.HTTPStatusError as exc:
            logger.error(
                "vLLM 請求失敗（%d）：%s", exc.response.status_code, exc.response.text
            )
            return ChatResponse(
                reply="",
                error=f"LLM 服務回傳錯誤 {exc.response.status_code}",
            )
        except Exception as exc:
            logger.error("vLLM 連線失敗：%s", exc)
            return ChatResponse(reply="", error=f"無法連線至 LLM 服務：{exc}")

        # 解析第一次回應
        try:
            data = resp.json()
        except Exception as exc:
            logger.error("vLLM 第一次回應解析失敗：%s  body=%s", exc, resp.text[:500])
            return ChatResponse(reply="", error="LLM 回應格式錯誤（非 JSON）")

        choices = data.get("choices") or []
        if not choices:
            logger.error("vLLM 第一次回應 choices 為空：%s", data)
            return ChatResponse(reply="", error="LLM 回傳空回應（choices 為空）")

        assistant_msg = choices[0].get("message") or {}
        messages.append(assistant_msg)

        tool_calls = assistant_msg.get("tool_calls") or []

        # ── 執行工具 ─────────────────────────────────────────────────────
        if tool_calls:
            # 只收集一次快照，所有工具共用
            try:
                _snapshot = await asyncio.to_thread(collect_snapshot)
            except Exception as exc:
                logger.error("收集 PVE 快照失敗：%s", exc)
                return ChatResponse(reply="", error=f"收集 PVE 資料失敗：{exc}")

            for tc in tool_calls:
                func_name: str = tc["function"]["name"]
                try:
                    func_args: dict = json.loads(
                        tc["function"].get("arguments") or "{}"
                    )
                except json.JSONDecodeError:
                    func_args = {}

                logger.info("執行工具 %s，參數：%s", func_name, func_args)
                tools_called.append(ToolCallRecord(name=func_name, args=func_args))

                try:
                    result = _execute_tool_sync(_snapshot, func_name, func_args)
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

        # ── 第二次請求：取得最終回答（僅在有工具呼叫時） ────────────────
        if tool_calls:
            payload2: dict[str, Any] = {
                "model": settings.vllm_model_name,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 4096,
            }
            try:
                resp2 = await client.post(url, json=payload2, headers=headers)
                resp2.raise_for_status()
            except Exception as exc:
                logger.error("vLLM 第二次請求失敗：%s", exc)
                return ChatResponse(
                    reply="",
                    tools_called=tools_called,
                    error=f"取得最終回答失敗：{exc}",
                )

            # 解析第二次回應
            try:
                data2 = resp2.json()
            except Exception as exc:
                logger.error(
                    "vLLM 第二次回應解析失敗：%s  body=%s", exc, resp2.text[:500]
                )
                return ChatResponse(
                    reply="",
                    tools_called=tools_called,
                    error="LLM 第二次回應格式錯誤（非 JSON）",
                )

            choices2 = data2.get("choices") or []
            reply = (
                (choices2[0].get("message") or {}).get("content") or ""
                if choices2
                else ""
            )
            if not choices2:
                logger.error("vLLM 第二次回應 choices 為空：%s", data2)
        else:
            reply = assistant_msg.get("content") or ""

    return ChatResponse(reply=reply, tools_called=tools_called)
