from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.recommendation import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DeviceNode,
    ExtractedIntent,
    RecommendationRequest,
)
from app.services.backend_nodes_service import summarize_device_nodes
from app.services.catalog_service import (
    TemplateCatalog,
    TemplateItem,
    build_catalog_prompt_bundle,
    catalog_lookup,
    find_explicit_template_matches,
    suggest_support_templates,
)


def _extract_user_signal_flags(messages: list[ChatMessage]) -> dict[str, bool]:
    user_text = "\n".join(
        str(m.content)
        for m in messages
        if str(m.role).strip().lower() == "user"
    ).lower()

    windows_keywords = (
        "windows",
        "win11",
        "win10",
        "rdp",
        "remote desktop",
        "遠端桌面",
        "圖形化",
        "gui",
        "桌面環境",
    )
    gpu_keywords = (
        "gpu",
        "cuda",
        "pytorch",
        "tensorflow",
        "llm",
        "stable diffusion",
        "comfyui",
        "ai",
        "模型推論",
        "訓練",
    )
    database_keywords = (
        "database",
        "db",
        "mysql",
        "postgres",
        "postgresql",
        "mariadb",
        "mongodb",
        "redis",
        "資料庫",
        "sql",
        "登入",
    )
    public_web_keywords = (
        "public",
        "internet",
        "external",
        "domain",
        "公開",
        "對外",
        "外網",
        "網址",
        "網域",
        "讓別人連",
    )

    def _contains_any(keywords: tuple[str, ...]) -> bool:
        return any(keyword in user_text for keyword in keywords)

    return {
        "needs_windows": _contains_any(windows_keywords),
        "requires_gpu": _contains_any(gpu_keywords),
        "needs_database": _contains_any(database_keywords),
        "needs_public_web": _contains_any(public_web_keywords),
    }


def _strip_think_tags(text: str) -> str:
    """Keep only the content after </think>. If the tag is absent, return text as-is."""
    marker = "</think>"
    idx = text.find(marker)
    if idx != -1:
        return text[idx + len(marker):].strip()
    return text.strip()


def _apply_thinking_control(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Pass Qwen/vLLM thinking control through the OpenAI-compatible request.
    When disabled, ask the model to skip reasoning output so responses return faster.
    """
    payload["chat_template_kwargs"] = {
        **dict(payload.get("chat_template_kwargs") or {}),
        "enable_thinking": settings.vllm_enable_thinking,
    }
    return payload


async def generate_chat_reply(request: ChatRequest) -> ChatResponse:
    if not settings.vllm_model_name:
        raise HTTPException(status_code=503, detail="VLLM_MODEL_NAME is required for AI planning.")

    is_first_turn = len(request.messages) <= 1
    greeting_instruction = (
        "- **Greeting (First Turn)**: Since this is the start of the conversation, act as a professional AI assistant (e.g., Gemini) and start with a warm, enthusiastic greeting (e.g.,「你好！很高興能為您服務」)."
        if is_first_turn else
        "- **Greeting (Subsequent Turns)**: You are already in the middle of a conversation. DO NOT repeat greetings or pleasantries (e.g., do not say \"你好\" again). Transition immediately into the topic and respond directly."
    )

    system_prompt = f"""# Role
You are a friendly, expert AI infrastructure consultant for a campus cloud platform, acting similarly to an advanced AI assistant like Gemini.
Your primary objective is to clarify the user's infrastructure deployment needs through a natural, conversational chat.

# Context & Constraints
- **Target Audience**: Users range from complete beginners to experienced computing veterans. Assume they might not know what Virtual Machines (VMs), Docker/LXC Containers, or Linux OS are.
- **Explanation Style**: When introducing a technical concept (e.g., VM vs. LXC) FOR THE FIRST TIME, use a simple, concrete, and DIVERSE analogy from everyday life (dining, transportation, renting, etc.). Ensure technical terms remain accurate. IMPORTANT: DO NOT re-explain or repeatedly compare VMs and LXC in every single turn if you have already covered it earlier in the chat history. Once a concept is explained, treat it as understood unless the user is confused.
- **Consulting Flow**: When a user asks for a specific tool or service, first briefly acknowledge it and mention its mainstream usage or common deployment practices. Then, transition seamlessly into helping them plan by asking your targeted clarifying questions.
- **Platform Scope**: We only provision local on-premise Virtual Machines (VMs) and LXC containers for educational and research workloads. We DO NOT offer or recommend public clouds like AWS/GCP/Azure.
- **Interaction Rules**: If the user's request is vague, ask 1 to 3 targeted clarifying questions to guide them smoothly. Do not overwhelm them with a massive wall of questions.
- **Language Requirement**: Regardless of this prompt being in English, you MUST reply entirely in Traditional Chinese (zh-TW). Your tone should be encouraging, patient, and highly professional.
- **Reasoning Visibility**: Do not expose chain-of-thought, internal reasoning, scratchpad, or `<think>` content. Return only the final user-facing answer.
{greeting_instruction}
- DO NOT generate JSON. Just chat normally.
"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in request.messages:
        messages.append({"role": msg.role, "content": msg.content})

    payload = _apply_thinking_control({
        "model": settings.vllm_model_name,
        "messages": messages,
        "max_tokens": settings.vllm_chat_max_tokens,
        "temperature": settings.vllm_chat_temperature,
        "top_p": settings.vllm_top_p,
        "top_k": settings.vllm_top_k,
        "min_p": settings.vllm_min_p,
        "repetition_penalty": settings.vllm_repetition_penalty,
    })
    headers = {
        "Authorization": f"Bearer {settings.vllm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        started_at = perf_counter()
        async with httpx.AsyncClient(timeout=settings.vllm_timeout) as client:
            response = await client.post(
                f"{settings.vllm_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            
            elapsed_seconds = max(perf_counter() - started_at, 0.0)
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
            tokens_per_second = (completion_tokens / elapsed_seconds) if elapsed_seconds > 0 else 0.0

            content = data["choices"][0]["message"]["content"] or ""
            # Fallback: strip any remaining <think>...</think> the server may have emitted
            content = _strip_think_tags(content)
            
            return ChatResponse(
                reply=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                elapsed_seconds=round(elapsed_seconds, 3),
                tokens_per_second=round(tokens_per_second, 2),
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI chat failed: {exc}") from exc


async def extract_intent_from_chat(request: ChatRequest) -> ExtractedIntent:
    if not settings.vllm_model_name:
        raise HTTPException(status_code=503, detail="VLLM_MODEL_NAME is required for AI planning.")

    recent_messages = request.messages[-10:]
    user_messages: list[str] = []
    full_chat_history: list[str] = []

    for m in recent_messages:
        normalized_role = str(m.role).strip().lower()
        if normalized_role == "user":
            user_messages.append(f"User: {m.content}")
            full_chat_history.append(f"User: {m.content}")
        elif normalized_role == "assistant":
            full_chat_history.append(f"Assistant: {m.content}")

    formatted_user_history = "\n\n".join(user_messages) if user_messages else "(No user messages)"
    formatted_history = "\n\n".join(full_chat_history) if full_chat_history else "(No conversation history)"
    user_signal_flags = _extract_user_signal_flags(recent_messages)

    prompt = f"""# Role
You are an expert "Intent Extractor". Your task is to accurately extract the user's final architectural requirements from a conversation history.

# Primary User Signals (Highest Priority)
{formatted_user_history}

# Full Conversation History (Reference)
{formatted_history}

# Keyword Detection Hints
System detected the following potential keywords in the user's recent messages:
- Needs Windows/GUI: {user_signal_flags["needs_windows"]}
- Requires GPU: {user_signal_flags["requires_gpu"]}
- Needs Database: {user_signal_flags["needs_database"]}
- Needs Public Web: {user_signal_flags["needs_public_web"]}

# Task
Analyze the conversation above. If there are conflicting statements, trust the LATEST user decision.
Prioritize "Primary User Signals" over assistant suggestions/questions.
Consider the "Keyword Detection Hints" as potential needs, but you MUST evaluate the conversation context to determine if the user ACTUALLY still wants them. If the user used a negation or changed their mind (e.g., "I don't need X anymore"), you MUST output false for that requirement.
Extract their requirements into a strict JSON object that matches the Output Schema.
Do not reveal chain-of-thought, internal reasoning, scratchpad, or `<think>` content.

# Output Schema constraints
- `goal_summary`: Highly technically descriptive summary (around 50-150 words) of their finalized requirement and background. Must be in Traditional Chinese.
- `role`: "student" or "teacher". (Default: student)
- `course_context`: "coursework", "teaching", or "research". (Default: coursework)
- `budget_mode`: "resource-saving", "balanced", or "performance". (Default: balanced)
- `needs_public_web`: boolean. True if they mention needing a public IP, external domain, or web access.
- `needs_database`: boolean. True if they mention storing data, a database, SQL, login systems, etc.
- `requires_gpu`: boolean. True if they mention AI, training, inference, PyTorch, Stable Diffusion, LLM, etc.
- `needs_windows`: boolean. True if they mention Remote Desktop (RDP), Windows, or strict GUI tools.

# Output Format
Output ONLY valid JSON matching the exact keys and types specified.
"""

    payload = _apply_thinking_control({
        "model": settings.vllm_model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    })
    headers = {
        "Authorization": f"Bearer {settings.vllm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.vllm_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return ExtractedIntent(**parsed)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {exc}") from exc


async def generate_ai_plan(
    request: RecommendationRequest,
    nodes: list[DeviceNode],
    template_catalog: TemplateCatalog,
    chat_history: list[ChatMessage],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not settings.vllm_model_name:
        raise HTTPException(status_code=503, detail="VLLM_MODEL_NAME is required for AI planning.")

    # Using directly extracted `needs_database`
    inferred_needs_database = request.needs_database

    prompt_bundle = build_catalog_prompt_bundle(
        template_catalog,
        request.goal,
        request.top_k,
        needs_public_web=request.needs_public_web,
        needs_database=inferred_needs_database,
    )
    user_context = {
        "goal": request.goal,
        "role": request.role,
        "course_context": request.course_context,
        "budget_mode": request.budget_mode,
        "needs_public_web": request.needs_public_web,
        "needs_database": request.needs_database,
        "requires_gpu": request.requires_gpu,
        "needs_windows": request.needs_windows,
        "inferred_needs_database": inferred_needs_database,
    }

    plan_schema = {
        "summary": "Traditional Chinese summary",
        "workload_profile": "one of: lightweight | moderate | compute-intensive | gpu-required | storage-heavy",
        "recommended_templates": [
            {"slug": "template-slug", "name": "template-name", "why": "Traditional Chinese reason (referencing specific context from the user intent)"}
        ],
        "possible_needed_templates": [
            {"slug": "template-slug", "name": "template-name", "why": "Traditional Chinese reason"}
        ],
        "machines": [
            {
                "name": "string",
                "purpose": "Traditional Chinese short phrase",
                "template_slug": "string",
                "deployment_type": "lxc|vm",
                "cpu": "integer",
                "memory_mb": "integer",
                "disk_gb": "integer",
                "gpu": "integer (0 or more)",
                "assigned_node": "node-name-or-null",
                "why": "Traditional Chinese reason (referencing specific context from the user intent)",
            }

        ],
        "overall_config": {
            "deployment_strategy": "Traditional Chinese short sentence",
            "machine_count": "integer",
            "total_cpu": "integer",
            "total_memory_mb": "integer",
            "total_disk_gb": "integer",
        },
        "decision_factors": ["Traditional Chinese short bullet"],
        "upgrade_when": "Traditional Chinese upgrade timing with specific metrics (e.g., RAM > 80%, CPU sustained > 70%)",
    }

    prompt = f"""# Role
You are an expert infrastructure planning AI for a campus cloud platform.

# Background Context
- This platform provisions local on-premise Virtual Machines (VMs) and LXC containers for educational, teaching, and research workloads.
- We DO NOT use, recommend, or refer to public clouds like AWS, GCP, or Azure. We directly assign our own local nodes to users.

# Task
Generate a complete deployment recommendation based on the user's intent, available hardware nodes, and valid template catalog. You must ONLY output valid JSON.

# Constraints & Rules
- **Language & Tone**: All natural-language fields MUST be written in Traditional Chinese (zh-TW). Avoid Simplified Chinese. Use a professional yet conversational and approachable tone (口語化、精準且自然的語氣), avoiding overly rigid, dry, or robotic phrasing.
- **Overall Summary (`summary`)**: This field must comprehensively summarize the entire plan in 3 to 4 sentences (approx. 100-120 chars). Explain *why* this architecture was chosen, how it fulfills the user's specific request, and briefly mention the future scaling or resource strategy. This is the main explanation presented to the user.
- **Explanation Depth (`why` fields)**: For each `why` field (in recommended_templates, possible_needed_templates, and machines), keep it concise but precise, roughly 1 to 2 sentences (approx. 40-60 chars). Directly explain why this specific template/resource is needed and how its configured CPU/RAM/Disk supports the workload. Do not repeat the general summary here.
- **Valid Templates**: Use ONLY template slugs from the provided `Template Catalog Bundle`. DO NOT invent templates.
- **Template Separation**: `recommended_templates` MUST be highly precise and contain ONLY the strictly necessary core templates directly required to fulfill the user's explicit request. Do not over-recommend here. `possible_needed_templates` MUST proactively anticipate future needs, scaling, and operational maturity. Think expansively and TRY YOUR BEST to recommend up to 3 extensible/support templates (e.g., databases, reverse proxy/NPM, monitoring, secret managers, caching, or backup solutions) that would greatly benefit their architecture. State why they are highly recommended in the `why` field.
- **Requirement Flags & Context**: You MUST STRICTLY honor request flags and user's specific context derived from the `User Context`.
  * `needs_public_web=true`: include public-entry components (e.g., reverse proxy or web gateway).
  * `needs_database=true` or `inferred_needs_database=true`: include suitable database support.
  * `requires_gpu=true`: fulfill GPU requirements in the plan.
  * `needs_windows=true`: the user requires a Windows or GUI environment.
- **Deployment Type Decision Tree** (apply in strict priority order):
  1. If `needs_windows=true` AND this is the **PRIMARY core service** → `deployment_type: "vm"`. Briefly explain in its `why` field (e.g., "配合 Windows/圖形化介面需求，將核心服務配置於 VM 環境"). DO NOT split the core service into LXC + a separate Windows VM.
  2. If a machine has `gpu >= 1`, or its template is an AI-heavy tool (e.g., ComfyUI, Ollama, PyTorch, Stable Diffusion, Jupyter), or it requires a GUI desktop → `deployment_type: "vm"`. State this clearly in `summary` and the machine's `why` field. DO NOT claim LXC for GPU or GUI machines.
  3. If the architecture requires 3+ tightly-coupled Docker containers or complex Docker-in-Docker → consolidate into `deployment_type: "vm"`.
  4. **All other cases** (including secondary supporting services such as databases, reverse proxies, caches, monitoring) → `deployment_type: "lxc"` to conserve resources. Do NOT transform secondary services into VMs even when `needs_windows=true`.
  Note: VM templates are currently placeholders ("無模板"), but you MUST output `vm` when architecturally required.
- **Resource Adjustments & AI Judgment**: You possess full authority to independently assess and allocate CPU, memory, Disk, and GPU. Do not strictly rely on template defaults—intelligently scale or reduce CPU and RAM based on the described intent context. For GPU, if the workload intrinsically benefits from or strictly requires a GPU for optimal running (e.g., ComfyUI, Large Language Models, PyTorch, AI/ML tools), YOU MUST output `gpu: 1` (or more) even if `requires_gpu=false`. Scale hardware intelligently and explain in `why`.
- **Upgrade Timing (`upgrade_when`)**: Reference specific measurable thresholds. For example: "當 CPU 使用率持續 > 70%、RAM 使用率 > 80%，或磁碟剩餘空間 < 15% 時，建議擴充資源或拆分服務。" Avoid vague language such as "當使用量增加時".
- **Tool Preference**: If the user clearly requests a specific tool and it's in the catalog, prioritize it over alternatives.
- **Capacity Constraints**: If current node capacity is insufficient for the ideal plan, reflect these limits in `summary`, `machines.why`, `overall_config.deployment_strategy`, or `upgrade_when`.
- **Output Format**: Output exactly the JSON structure defined in `Output Schema`. Do not wrap with natural language conversational responses.
- **Reasoning Visibility**: Do not reveal chain-of-thought, internal reasoning, scratchpad, or `<think>` content. Return only the final JSON object.

# Input Data
## User Context (Extracted summary)
{json.dumps(user_context, ensure_ascii=False)}

## Node Capacity Summary
{json.dumps(summarize_device_nodes(nodes), ensure_ascii=False)}

## Template Catalog Bundle
{json.dumps(prompt_bundle, ensure_ascii=False)}

# Output Schema
{json.dumps(plan_schema, ensure_ascii=False)}"""

    payload = _apply_thinking_control({
        "model": settings.vllm_model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.vllm_max_tokens,
        "temperature": settings.vllm_temperature,
        "top_p": settings.vllm_top_p,
        "top_k": settings.vllm_top_k,
        "min_p": settings.vllm_min_p,
        "presence_penalty": settings.vllm_presence_penalty,
        "repetition_penalty": settings.vllm_repetition_penalty,
        "response_format": {"type": "json_object"},
    })
    headers = {
        "Authorization": f"Bearer {settings.vllm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        started_at = perf_counter()
        async with httpx.AsyncClient(timeout=settings.vllm_timeout) as client:
            response = await client.post(
                f"{settings.vllm_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            elapsed_seconds = max(perf_counter() - started_at, 0.0)
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
            # 使用 completion_tokens 計算生成速度（排除 prompt 輸入部分，反映真實推論吞吐量）
            tokens_per_second = (completion_tokens / elapsed_seconds) if elapsed_seconds > 0 else 0.0

            metrics = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "tokens_per_second": round(tokens_per_second, 2),
            }
            return json.loads(data["choices"][0]["message"]["content"]), metrics
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI planning failed: {exc}") from exc


def normalize_ai_result(
    ai_result: dict[str, Any],
    request: RecommendationRequest,
    nodes: list[DeviceNode],
    template_catalog: TemplateCatalog,
) -> dict[str, Any]:
    lookup = catalog_lookup(template_catalog)
    explicit_matches = find_explicit_template_matches(template_catalog, request.goal)
    machines: list[dict[str, Any]] = []
    recommended_templates: list[dict[str, Any]] = []
    possible_needed_templates: list[dict[str, Any]] = []
    decision_factors = [
        str(item).strip()
        for item in list(ai_result.get("decision_factors") or [])
        if str(item).strip()
    ]

    for item in list(ai_result.get("recommended_templates") or []):
        normalized = _normalize_template_choice(item, lookup)
        if normalized and not any(existing["slug"] == normalized["slug"] for existing in recommended_templates):
            recommended_templates.append(normalized)

    for item in list(ai_result.get("possible_needed_templates") or []):
        normalized = _normalize_template_choice(item, lookup, fallback_why="AI 判斷這是後續擴充或公開服務常見的支援模板。")
        if not normalized:
            continue
        if any(existing["slug"] == normalized["slug"] for existing in recommended_templates):
            continue
        if any(existing["slug"] == normalized["slug"] for existing in possible_needed_templates):
            continue
        possible_needed_templates.append(normalized)

    for machine in list(ai_result.get("machines") or []):
        slug = str(machine.get("template_slug") or "").strip().lower()
        template = lookup.get(slug)
        if not template:
            continue
        machines.append(_normalize_machine(machine, template, request_requires_gpu=request.requires_gpu, request_needs_windows=request.needs_windows))

    _promote_explicit_templates(
        recommended_templates,
        possible_needed_templates,
        explicit_matches,
    )
    _align_machine_templates_with_explicit_matches(machines, explicit_matches, lookup, request)

    if not recommended_templates:
        for machine in machines:
            template = lookup.get(str(machine.get("template_slug") or "").strip().lower())
            if not template:
                continue
            if any(existing["slug"] == template.slug for existing in recommended_templates):
                continue
            recommended_templates.append(
                {
                    "slug": template.slug,
                    "name": template.name,
                    "why": "AI 在最終配置中實際使用此模板。",
                }
            )

    # 移除對 AI 推薦支援模板的硬性截斷到 2 個的限制，允許 AI 的前 3 個推薦完整保留。
    possible_needed_templates = possible_needed_templates[:3]
    _append_support_template_fallbacks(
        possible_needed_templates,
        recommended_templates,
        request,
        template_catalog,
    )

    computed_summary = {
        "machine_count": len(machines),
        "total_cpu": sum(int(machine.get("cpu") or 0) for machine in machines),
        "total_memory_mb": sum(int(machine.get("memory_mb") or 0) for machine in machines),
        "total_disk_gb": sum(int(machine.get("disk_gb") or 0) for machine in machines),
        "public_endpoints": sum(
            1 for machine in machines if str(machine.get("purpose", "")).lower() in {"edge", "proxy", "gateway"}
        ),
    }
    overall_config = dict(ai_result.get("overall_config") or {})
    overall_config = {
        "deployment_strategy": overall_config.get("deployment_strategy") or "由 AI 根據需求、節點容量與模板能力整理的整體部署策略。",
        "machine_count": int(overall_config.get("machine_count") or computed_summary["machine_count"]),
        "total_cpu": int(overall_config.get("total_cpu") or computed_summary["total_cpu"]),
        "total_memory_mb": int(overall_config.get("total_memory_mb") or computed_summary["total_memory_mb"]),
        "total_disk_gb": int(overall_config.get("total_disk_gb") or computed_summary["total_disk_gb"]),
    }

    possible_needed_templates = possible_needed_templates[:3]

    final_plan = {
        "summary": computed_summary,
        "machines": machines,
        "recommended_templates": recommended_templates,
        "possible_needed_templates": possible_needed_templates,
        "overall_config": overall_config,
    }

    return {
        "persona": {
            "role": request.role,
            "course_context": request.course_context,
            "sharing_scope": request.sharing_scope,
            "budget_mode": request.budget_mode,
        },
        "workload_profile": ai_result.get("workload_profile") or "ai-planned",
        "scenario_label": (
            "research-grade"
            if request.course_context == "research"
            else "teaching-service"
            if request.course_context == "teaching"
            else "student-project"
        ),
        "device_profile": summarize_device_nodes(nodes),
        "final_plan": final_plan,
        "recommended_path": {
            "fit": "ai-generated plan",
            "why": [item.get("why") for item in recommended_templates if item.get("why")] or ["AI 依據需求、設備與模板資訊直接規劃。"],
            "upgrade_when": ai_result.get("upgrade_when") or "",
        },
        "rule_basis": {
            "reasons": decision_factors or ["AI 直接根據需求、節點容量與模板清單做整體規劃。"],
            "capacity_checks": [
                {
                    "machine": machine.get("name"),
                    "assigned_node": machine.get("assigned_node"),
                    "status": "ai-assigned",
                }
                for machine in machines
            ],
        },
        "summary": ai_result.get("summary") or "",
    }


def _normalize_machine(
    machine: dict[str, Any],
    template: TemplateItem,
    *,
    request_requires_gpu: bool = False,
    request_needs_windows: bool = False,
) -> dict[str, Any]:
    def _safe_int(value: Any, default: int) -> int:
        """
        Safely convert a value to int, falling back to the provided default on
        TypeError or ValueError. This defends against AI-provided strings like
        "2 vCPU" or "4GB" that cannot be parsed directly by int().
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    install_methods = template.raw.get("install_methods") or []
    default_resources = dict((install_methods[0].get("resources") or {})) if install_methods else {}
    default_cpu = _safe_int(default_resources.get("cpu"), 1)
    default_ram_mb = _safe_int(default_resources.get("ram"), 1024)
    default_disk_gb = _safe_int(default_resources.get("hdd"), 10)

    cpu_value = machine.get("cpu")
    memory_value = machine.get("memory_mb")
    disk_value = machine.get("disk_gb")
    gpu_value = machine.get("gpu")

    # Allow AI to decide CPU/RAM/Disk, using 1/256/2 as absolute minimums, relying on default if missing.
    cpu = max(_safe_int(cpu_value, default_cpu), 1)
    memory_mb = max(_safe_int(memory_value, default_ram_mb), 256)
    disk_gb = max(_safe_int(disk_value, default_disk_gb), 2)

    # Let AI decide GPU natively based on its system prompt judgment.
    # Default fallback to 1 only if user globally checked requires_gpu and AI omitted the key.
    fallback_gpu = 1 if request_requires_gpu else 0
    if gpu_value is not None:
        gpu = max(_safe_int(gpu_value, fallback_gpu), 0)
    else:
        gpu = fallback_gpu

    ai_deployment_type = str(machine.get("deployment_type") or "").strip().lower()
    complex_vm_keywords = {"comfy", "ollama", "llm", "stable", "pytorch", "jupyter"}
    gui_vm_keywords = {"windows", "desktop", "gui", "ubuntu-desktop"}
    
    # 強制防呆：只要有配置 GPU、屬於已知複雜 AI 服務或明確為 GUI 系統，一律轉為 VM
    if gpu >= 1 or any(kw in template.slug.lower() for kw in complex_vm_keywords | gui_vm_keywords):
        deployment_type = "vm"
    else:
        deployment_type = "vm" if ai_deployment_type == "vm" else "lxc"

    return {
        "name": machine.get("name") or f"{template.slug}-node",
        "purpose": machine.get("purpose") or "應用服務",
        "template_slug": template.slug,
        "deployment_type": deployment_type,
        "cpu": cpu,
        "memory_mb": memory_mb,
        "disk_gb": disk_gb,
        "gpu": gpu,
        "assigned_node": machine.get("assigned_node"),
        "why": machine.get("why") or "AI 依需求與設備容量規劃此部署單位。",
        "default_resources": {
            "cpu": default_cpu,
            "memory_mb": default_ram_mb,
            "disk_gb": default_disk_gb,
        },
    }


def _normalize_template_choice(
    item: dict[str, Any],
    lookup: dict[str, TemplateItem],
    *,
    fallback_why: str = "AI 依需求選擇此核心模板。",
) -> dict[str, Any] | None:
    slug = str(item.get("slug") or "").strip().lower()
    template = lookup.get(slug)
    if not template:
        return None
    return {
        "slug": template.slug,
        "name": template.name,
        "why": item.get("why") or fallback_why,
    }


def _append_support_template_fallbacks(
    possible_needed_templates: list[dict[str, Any]],
    recommended_templates: list[dict[str, Any]],
    request: RecommendationRequest,
    template_catalog: TemplateCatalog,
) -> None:
    used_slugs = {item["slug"] for item in recommended_templates} | {item["slug"] for item in possible_needed_templates}
    effective_needs_database = request.needs_database

    if effective_needs_database and len(possible_needed_templates) < 3:
        database_candidates = suggest_support_templates(
            template_catalog,
            needs_public_web=False,
            needs_database=True,
        )
        _append_first_unused_template(
            possible_needed_templates,
            database_candidates,
            used_slugs,
            "因已勾選需要資料庫，補列一個資料庫支援模板供部署時參考。",
        )

    if request.needs_public_web:
        edge_candidates = suggest_support_templates(
            template_catalog,
            needs_public_web=True,
            needs_database=False,
        )
        _append_first_unused_template(
            possible_needed_templates,
            edge_candidates,
            used_slugs,
            "因服務需對外開放，補列一個公開入口或代理模板供部署時參考。",
        )

    if request.requires_gpu:
        gpu_candidates = _suggest_gpu_templates(template_catalog)
        _append_first_unused_template(
            possible_needed_templates,
            gpu_candidates,
            used_slugs,
            "因已勾選需要顯卡，補列一個 GPU 相關模板供部署與擴充時參考。",
        )


def _suggest_gpu_templates(template_catalog: TemplateCatalog) -> list[TemplateItem]:
    gpu_keywords = (
        "gpu",
        "cuda",
        "pytorch",
        "tensorflow",
        "nvidia",
        "ollama",
        "llm",
        "whisper",
        "stable",
        "comfy",
        "jupyter",
    )
    matches: list[TemplateItem] = []
    for item in template_catalog.items:
        haystack = " ".join((item.slug, item.name, item.description)).lower()
        if any(keyword in haystack for keyword in gpu_keywords):
            matches.append(item)
    return matches


def _append_first_unused_template(
    target: list[dict[str, Any]],
    candidates: list[TemplateItem],
    used_slugs: set[str],
    why: str,
) -> None:
    for template in candidates:
        if template.slug in used_slugs:
            continue
        target.append(
            {
                "slug": template.slug,
                "name": template.name,
                "why": why,
            }
        )
        used_slugs.add(template.slug)
        return


def _promote_explicit_templates(
    recommended_templates: list[dict[str, Any]],
    possible_needed_templates: list[dict[str, Any]],
    explicit_matches: list[TemplateItem],
) -> None:
    if not explicit_matches:
        return

    existing_core_slugs = {item["slug"] for item in recommended_templates}
    existing_support_slugs = {item["slug"] for item in possible_needed_templates}
    explicit_core_items: list[dict[str, Any]] = []

    for template in explicit_matches:
        if template.slug in existing_core_slugs:
            explicit_core_items.append(next(item for item in recommended_templates if item["slug"] == template.slug))
            continue

        if template.slug in existing_support_slugs:
            moved_item = next(item for item in possible_needed_templates if item["slug"] == template.slug)
            possible_needed_templates[:] = [item for item in possible_needed_templates if item["slug"] != template.slug]
            moved_item["why"] = "使用者需求中明確提到此工具，已提升為核心模板。"
            explicit_core_items.append(moved_item)
            continue

        explicit_core_items.append(
            {
                "slug": template.slug,
                "name": template.name,
                "why": "使用者需求中明確提到此工具，已提升為核心模板。",
            }
        )

    if explicit_core_items:
        explicit_slugs = {item["slug"] for item in explicit_core_items}
        remaining_core = [item for item in recommended_templates if item["slug"] not in explicit_slugs]
        recommended_templates[:] = explicit_core_items + remaining_core


def _align_machine_templates_with_explicit_matches(
    machines: list[dict[str, Any]],
    explicit_matches: list[TemplateItem],
    lookup: dict[str, TemplateItem],
    request: RecommendationRequest,
) -> None:
    if not machines or not explicit_matches:
        return

    machine_template_slugs = {str(machine.get("template_slug") or "").strip().lower() for machine in machines}
    if machine_template_slugs & {template.slug for template in explicit_matches}:
        return

    primary_template = explicit_matches[0]
    primary_machine = machines[0]
    # Bug 3: 改用 .get() 防止 slug 不在 lookup 時拋出 KeyError
    template_obj = lookup.get(primary_template.slug.lower())
    if not template_obj:
        return
    normalized = _normalize_machine(primary_machine, template_obj, request_requires_gpu=request.requires_gpu, request_needs_windows=request.needs_windows)
    normalized["name"] = primary_machine.get("name") or f"{primary_template.slug}-node"
    normalized["purpose"] = primary_machine.get("purpose") or normalized["purpose"]
    normalized["assigned_node"] = primary_machine.get("assigned_node")
    normalized["why"] = "使用者需求中明確指定此工具，已將主要部署單位對齊為對應模板。"
    machines[0] = normalized
