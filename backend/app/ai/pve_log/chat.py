"""AI 對話服務 — vLLM Tool Calling（支援 Gemma-4 / Qwen3 等模型）

流程：
  1. 帶著工具定義向 vLLM 發出請求
  2. 若 AI 回傳 tool_calls，逐一執行：
     - PVE 工具：內部呼叫 collector，不走 HTTP
     - ssh_exec：呼叫 SkyLab API 取得 SSH key，SSH 進入 VM 執行
  3. 將工具結果加回 messages，持續進行下一個 agent step
  4. 遇到人工確認時中斷；確認後由呼叫端帶著同一份 messages 恢復
  5. AI 產生最終回答後回傳 ChatResponse

設計重點：
  - 一次 chat 請求只收集一次 PVE 快照（lazy），多個 tool_calls 共用同一份快照。
  - 工具可連續呼叫多輪，但有固定上限，避免模型陷入無限工具迴圈。
  - 一般 ssh_exec 需要確認；template 僅允許伺服器列出的唯讀指令自動執行。
  - 若呼叫端提供 VMID 範圍，工具輸出與 SSH 執行都只允許該範圍。
  - Gemma-4/Qwen3 的 <think> 與 tool call 標記會在每個 agent step 前清除，
    避免 message history 污染導致 LLM 無法正確總結。
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
import uuid
from typing import Any

import httpx
from sqlmodel import Session

from app.ai.pve_log.collector import collect_snapshot
from app.ai.pve_log.config import settings
from app.ai.pve_log.schemas import ChatResponse, SystemSnapshot, ToolCallRecord
from app.ai.pve_tools.definitions import build_tool_definitions
from app.ai.pve_tools.executor import execute_guest_check
from app.ai.pve_tools.registry import resolve_profile
from app.infrastructure.ai.pve_log import client as vllm_client

logger = logging.getLogger(__name__)
_MAX_TOOL_ROUNDS = 6

# ---------------------------------------------------------------------------
# 系統提示詞
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是 SkyLab PVE 管理助手，專門協助管理員查詢 Proxmox VE 虛擬化平台的資源狀態。

工具使用原則：
- 問題只涉及一種資源時，優先呼叫最精確的工具（例如只查儲存空間就用 get_storage，不要呼叫 get_resources）。
- 需要特定 VM/LXC 詳情時才呼叫 get_resource_detail，並傳入正確的 vmid。
- 若問題同時涉及多類資料，可以在同一輪呼叫多個工具。

SSH 工具（ssh_exec）使用原則：
- **優先使用 PVE API 工具**，PVE API 已可取得 CPU、記憶體、磁碟、網路的即時使用率。
- 只有在 PVE API 無法取得足夠細節時，才使用 ssh_exec。
- **適合 SSH 的場景**：程序列表（ps aux）、服務狀態（systemctl status）、
  詳細日誌（journalctl）、Python 環境查詢、自訂腳本執行、
  應用層資訊（nginx、docker、資料庫等）。
- **指令風格**：保持簡單實用，優先使用單行指令；Python 片段以 python3 -c '...' 格式。
- **必填 reason**：每次呼叫 ssh_exec 必須在 reason 欄位說明執行目的，
  讓使用者在確認對話中做出知情決策。
- 需要 ssh_exec 時直接呼叫工具，不要先用文字詢問使用者是否同意，也不要在回覆中只展示
  指令等待使用者再次要求。後端會自動判定直接執行、等待確認或 hard-deny。
- 被攔截的危險指令（如 rm -rf）無法執行。

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

_TOOLS: list[dict[str, Any]] = [
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
    {
        "type": "function",
        "function": {
            "name": "ssh_exec",
            "description": (
                "透過 SSH 連線到指定 VMID 的 VM/LXC，執行遠端指令取得內部系統細節或執行管理操作。"
                "可執行任意 shell 指令或 Python 腳本片段。"
                "PVE API 工具無法提供足夠細節時才使用（如程序列表、服務狀態、日誌、Python 環境等）。"
                "模型應直接呼叫本工具，不得先用自然語言詢問是否同意。"
                "後端會判定直接執行或回傳待確認；危險指令會被黑名單直接攔截。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vmid": {
                        "type": "integer",
                        "description": "目標 VM 或 LXC 的 VMID",
                    },
                    "command": {
                        "type": "string",
                        "description": (
                            "要在遠端執行的指令（保持簡單實用）。"
                            "範例：ps aux | grep python、df -h、free -m、"
                            "systemctl status nginx、journalctl -n 50 --no-pager、"
                            "python3 -c 'import sys; print(sys.version)'"
                        ),
                    },
                    "ssh_user": {
                        "type": "string",
                        "description": "SSH 登入帳號（預設 root）",
                    },
                    "ssh_port": {
                        "type": "integer",
                        "description": "SSH 埠號（預設 22）",
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "說明為何需要執行此指令（必填），顯示給使用者作為確認依據。"
                            "例如：查詢 VM 101 內的 Python 程序列表、"
                            "取得 nginx 服務運行狀態"
                        ),
                    },
                },
                "required": ["vmid", "command", "reason"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool 執行器
# ---------------------------------------------------------------------------


def _execute_tool_sync(
    snapshot: SystemSnapshot,
    name: str,
    args: dict[str, Any],
    *,
    allowed_vmids: set[int] | None = None,
) -> Any:
    """使用已收集好的 snapshot 執行工具，同步版本（供 asyncio.to_thread 包裝）。"""
    if name == "get_nodes":
        return [n.model_dump(mode="json") for n in snapshot.nodes]

    elif name == "get_storage":
        storage_result = snapshot.storages
        if args.get("node"):
            storage_result = [s for s in storage_result if s.node == args["node"]]
        return [s.model_dump(mode="json") for s in storage_result]

    elif name == "get_resources":
        resource_result = snapshot.resources
        if args.get("node"):
            resource_result = [
                r for r in resource_result if r.node == args["node"]
            ]
        if args.get("resource_type"):
            resource_result = [
                r
                for r in resource_result
                if r.resource_type == args["resource_type"]
            ]
        if args.get("status"):
            resource_result = [
                r for r in resource_result if r.status == args["status"]
            ]
        if allowed_vmids is not None:
            resource_result = [
                r for r in resource_result if r.vmid in allowed_vmids
            ]
        return [r.model_dump(mode="json") for r in resource_result]

    elif name == "get_resource_detail":
        vmid = int(args["vmid"])
        if allowed_vmids is not None and vmid not in allowed_vmids:
            return {"error": "目前只允許存取指定範圍內的 VM/LXC"}
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


async def _execute_ssh_tool(
    args: dict[str, Any],
    *,
    session: Session | None = None,
    allowed_vmids: set[int] | None = None,
    requester_id: uuid.UUID | None = None,
    scope_type: str | None = None,
    scope_id: uuid.UUID | None = None,
    template_key: str | None = None,
) -> dict[str, Any]:
    """執行 ssh_exec 工具（async，需要等待 SSH 連線）。

    一般 PVE Log 呼叫會 pending；template 入口只讓伺服器列出的唯讀
    smoke command 自動執行，未知或自訂指令仍需人工確認。黑名單永遠先執行。
    """
    from app.ai.pve_log.schemas import SSHExecRequest as _SSHExecRequest
    from app.ai.pve_log.ssh_exec import ssh_exec as _ssh_exec

    try:
        vmid = int(args["vmid"])
        command = str(args["command"])
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"缺少或無效的必填參數: {e}", "pending": False}

    if allowed_vmids is not None and vmid not in allowed_vmids:
        return {
            "vmid": vmid,
            "host": "",
            "ssh_user": str(args.get("ssh_user", "root")),
            "command": command,
            "blocked": True,
            "block_reason": "目前只允許存取指定範圍內的 VM/LXC",
            "pending": False,
        }

    effective_ssh_user = (
        "root" if template_key else str(args.get("ssh_user", "root"))
    )
    req = _SSHExecRequest(
        vmid=vmid,
        command=command,
        ssh_user=effective_ssh_user,
        ssh_port=int(args.get("ssh_port", 22)),
        require_confirm=True,
    )
    result = await _ssh_exec(
        req,
        session=session,
        allowed_vmids=allowed_vmids,
        requester_id=requester_id,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    data = result.model_dump(mode="json")
    # 補充 reason 給前端顯示（AI 提供的說明）
    data["reason"] = str(args.get("reason", "未提供原因"))
    return data


def _normalize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    """Normalize native and Qwen text-encoded tool calls into one message shape."""
    assistant_msg = dict(message)
    raw_content = assistant_msg.get("content") or ""

    if not assistant_msg.get("tool_calls") and "call:" in raw_content:
        match = re.search(
            r"<\|?tool_call\|?>\s*call:([a-zA-Z0-9_]+)\s*(\{.+?\})\s*"
            r"<\|?/?tool_call\|?>",
            raw_content,
            flags=re.DOTALL,
        )
        if not match:
            match = re.search(
                r"<\|?tool_call\|?>\s*call:([a-zA-Z0-9_]+)\s*(\{.+\})",
                raw_content,
                flags=re.DOTALL,
            )
        if match:
            func_name = match.group(1)
            args_fixed = match.group(2).replace('<|"|>', '"')
            args_fixed = re.sub(
                r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)",
                r'\1"\2"\3',
                args_fixed,
            )
            try:
                parsed_args = json.loads(args_fixed)
                assistant_msg["tool_calls"] = [
                    {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "arguments": json.dumps(parsed_args, ensure_ascii=False),
                        },
                    }
                ]
                logger.info(
                    "成功手動解析 Qwen tool call: %s(%s)", func_name, parsed_args
                )
            except (TypeError, json.JSONDecodeError) as exc:
                logger.error(
                    "手動解析 Qwen tool call 失敗: %s, 修正後: %s",
                    exc,
                    args_fixed,
                )

    if not assistant_msg.get("tool_calls"):
        return assistant_msg

    cleaned = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL)
    cleaned = re.sub(
        r"<\|?tool_call\|?>\s*call:[a-zA-Z0-9_]+\s*\{.+?\}\s*"
        r"<\|?/?tool_call\|?>",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"<\|?tool_call\|?>\s*call:[a-zA-Z0-9_]+\s*\{.+\}",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"<\|tool_call\|>.*?<\|/tool_call\|>", "", cleaned, flags=re.DOTALL
    )
    cleaned = re.sub(
        r"<\|tool_call>.*?<tool_call\|>", "", cleaned, flags=re.DOTALL
    )
    cleaned = re.sub(
        r'```json\s*\{\s*"tool_call".*?```', "", cleaned, flags=re.DOTALL
    )
    cleaned = re.sub(r"<tool_call>.*?</tool_call>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<\|[^>]*\|>", "", cleaned)
    return {**assistant_msg, "content": cleaned.strip() or None}


def _parse_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}

    args_str = value.strip() or "{}"
    try:
        parsed = json.loads(args_str)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        args_str = args_str.replace('<|"|>', '"').replace("'", '"')
        args_str = re.sub(
            r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)",
            r'\1"\2"\3',
            args_str,
        )

    try:
        parsed = json.loads(args_str)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(args_str)
        except (SyntaxError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


_CONFIRMATION_PROSE_MARKERS = (
    "請確認是否同意執行",
    "是否同意執行以下指令",
    "是否允許執行以下指令",
    "若您同意，我將立即執行",
)


def _promote_confirmation_prose_to_tool_call(
    message: dict[str, Any],
    *,
    allowed_vmids: set[int] | None,
    template_key: str | None,
) -> dict[str, Any]:
    """Convert a template model's redundant prose confirmation into ssh_exec.

    This compatibility path is intentionally narrow: it only applies to a
    template-scoped, single-VM request that contains both an explicit approval
    prompt and one backticked command. The normal path remains native tool
    calling, and the server-side SSH guard/confirmation policy still decides
    whether the command may run.
    """
    if (
        message.get("tool_calls")
        or not template_key
        or allowed_vmids is None
        or len(allowed_vmids) != 1
    ):
        return message

    content = str(message.get("content") or "")
    if not any(marker in content for marker in _CONFIRMATION_PROSE_MARKERS):
        return message

    command_match = re.search(
        r"(?:\*\*)?\s*指令\s*[：:]\s*(?:\*\*)?\s*`([^`\r\n]+)`",
        content,
    )
    if command_match is None:
        return message

    command = command_match.group(1).strip()
    if not command or len(command) > 2000:
        return message

    reason_match = re.search(
        r"(?:\*\*)?\s*執行原因\s*[：:]\s*(?:\*\*)?\s*(.+?)(?:\r?\n|$)",
        content,
    )
    reason = (
        reason_match.group(1).strip().strip("*")
        if reason_match
        else "依 AI 診斷判斷執行此指令以取得 VM 內部狀態"
    )
    vmid = next(iter(allowed_vmids))
    logger.info(
        "將 template 文字確認轉為 ssh_exec tool call: template=%s vmid=%d",
        template_key,
        vmid,
    )
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": "ssh_exec",
                    "arguments": json.dumps(
                        {
                            "vmid": vmid,
                            "command": command,
                            "reason": reason,
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# 主對話函式
# ---------------------------------------------------------------------------


async def chat(
    message: str | None = None,
    history: list[dict[str, Any]] | None = None,
    *,
    session: Session | None = None,
    allowed_vmids: set[int] | None = None,
    requester_id: uuid.UUID | None = None,
    scope_type: str | None = None,
    scope_id: uuid.UUID | None = None,
    system_prompt: str | None = None,
    template_key: str | None = None,
) -> ChatResponse:
    """執行有限步數的 AI agent 對話，支援 tool calling、確認中斷及接續。"""
    if not settings.VLLM_BASE_URL or not settings.VLLM_MODEL_NAME:
        return ChatResponse(
            reply="",
            error="vLLM 設定不完整，請確認 .env 中的 VLLM_* 設定",
        )

    effective_system_prompt = system_prompt or _SYSTEM_PROMPT
    if history:
        if system_prompt is not None:
            messages = [
                dict(item)
                for item in history
                if isinstance(item, dict) and item.get("role") != "system"
            ]
            messages.insert(
                0,
                {"role": "system", "content": effective_system_prompt},
            )
            if allowed_vmids is not None:
                messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "本次對話僅可讀取與操作指定範圍內的 VM/LXC，"
                            "不得查詢或操作範圍外的 VMID。"
                        ),
                    },
                )
            if message:
                messages.append({"role": "user", "content": message})
        else:
            messages = [dict(item) for item in history]
    else:
        messages = [{"role": "system", "content": effective_system_prompt}]
        if allowed_vmids is not None:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "本次對話僅可讀取與操作指定範圍內的 VM/LXC，"
                        "不得查詢或操作範圍外的 VMID。"
                    ),
                }
            )
        if message:
            messages.append({"role": "user", "content": message})

    profile = resolve_profile(template_key) if template_key else None
    active_tools = build_tool_definitions(_TOOLS, profile)
    tools_called: list[ToolCallRecord] = []
    _snapshot: SystemSnapshot | None = None  # lazy，只有工具真的被呼叫時才收集

    for tool_round in range(_MAX_TOOL_ROUNDS + 1):
        payload: dict[str, Any] = {
            "model": settings.VLLM_MODEL_NAME,
            "messages": messages,
            "tools": active_tools,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        try:
            data = await vllm_client.create_chat_completion(
                payload,
                timeout=float(settings.VLLM_TIMEOUT),
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "vLLM 請求失敗（%d）：%s", exc.response.status_code, exc.response.text
            )
            return ChatResponse(
                reply="",
                tools_called=tools_called,
                messages=messages,
                error=f"LLM 服務回傳錯誤 {exc.response.status_code}",
            )
        except Exception as exc:
            logger.error("vLLM 連線失敗：%s", exc)
            return ChatResponse(
                reply="",
                tools_called=tools_called,
                messages=messages,
                error=f"無法連線至 LLM 服務：{exc}",
            )

        choices = data.get("choices") or []
        if not choices:
            logger.error("vLLM agent step %d 回應 choices 為空：%s", tool_round, data)
            return ChatResponse(
                reply="",
                tools_called=tools_called,
                messages=messages,
                error="LLM 回傳空回應（choices 為空）",
            )

        assistant_msg = _normalize_assistant_message(
            choices[0].get("message") or {}
        )
        assistant_msg = _promote_confirmation_prose_to_tool_call(
            assistant_msg,
            allowed_vmids=allowed_vmids,
            template_key=template_key,
        )
        messages.append(assistant_msg)
        tool_calls = assistant_msg.get("tool_calls") or []
        if not tool_calls:
            return ChatResponse(
                reply=assistant_msg.get("content") or "",
                tools_called=tools_called,
                messages=messages,
            )

        if tool_round >= _MAX_TOOL_ROUNDS:
            logger.error("AI 工具呼叫超過上限（%d 輪）", _MAX_TOOL_ROUNDS)
            return ChatResponse(
                reply="",
                tools_called=tools_called,
                messages=messages,
                error="AI 連續呼叫工具次數過多，已停止以避免無限迴圈。",
            )

        needs_snapshot = any(
            tc.get("function", {}).get("name")
            not in {"ssh_exec", "run_guest_check"}
            for tc in tool_calls
        )
        if needs_snapshot and _snapshot is None:
            try:
                _snapshot = await asyncio.to_thread(collect_snapshot)
            except Exception as exc:
                logger.error("收集 PVE 快照失敗：%s", exc)
                return ChatResponse(
                    reply="",
                    tools_called=tools_called,
                    messages=messages,
                    error=f"收集 PVE 資料失敗：{exc}",
                )

        needs_confirmation = False
        for tc in tool_calls:
            function = tc.get("function") or {}
            func_name = str(function.get("name") or "")
            func_args = _parse_tool_arguments(function.get("arguments") or "{}")
            logger.info(
                "執行工具（agent step %d）%s，參數：%s",
                tool_round,
                func_name,
                func_args,
            )

            try:
                if func_name == "ssh_exec":
                    result = await _execute_ssh_tool(
                        func_args,
                        session=session,
                        allowed_vmids=allowed_vmids,
                        requester_id=requester_id,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        template_key=template_key,
                    )
                elif func_name == "run_guest_check":
                    if profile is None:
                        result = {
                            "status": "rejected",
                            "error": "目前入口未啟用 guest-check profile",
                        }
                    else:
                        result = await execute_guest_check(
                            func_args,
                            profile=profile,
                            session=session,
                            allowed_vmids=allowed_vmids,
                            requester_id=requester_id,
                            scope_type=scope_type,
                            scope_id=scope_id,
                        )
                else:
                    if _snapshot is None:
                        raise RuntimeError("PVE snapshot 尚未完成收集")
                    result = _execute_tool_sync(
                        _snapshot,
                        func_name,
                        func_args,
                        allowed_vmids=allowed_vmids,
                    )
                result_dict = result if isinstance(result, dict) else {}
                needs_confirmation = (
                    needs_confirmation or bool(result_dict.get("pending"))
                )
                tool_content = json.dumps(result, ensure_ascii=False, default=str)
                tools_called.append(
                    ToolCallRecord(name=func_name, args=func_args, result=result_dict)
                )
            except Exception as exc:
                logger.error("工具 %s 執行失敗：%s", func_name, exc)
                tool_content = json.dumps({"error": str(exc)}, ensure_ascii=False)
                tools_called.append(
                    ToolCallRecord(
                        name=func_name,
                        args=func_args,
                        result={"error": str(exc)},
                    )
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "content": tool_content,
                }
            )

        if needs_confirmation:
            return ChatResponse(
                reply="有指令需要您的確認；同意或拒絕後，AI 會從目前步驟繼續。",
                tools_called=tools_called,
                needs_confirmation=True,
                messages=messages,
            )

    raise AssertionError("unreachable")
