from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.main_state import catalog
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
from app.services.prompt import (
    build_ai_plan_prompt,
    build_chat_catalog_context,
    build_chat_system_prompt,
    build_intent_extraction_prompt,
)

MIN_LXC_DISK_GB = 10
MIN_VM_DISK_GB = 20


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
    catalog_context = build_chat_catalog_context(
        catalog,
        request.messages,
        top_k=request.top_k,
    )
    system_prompt = build_chat_system_prompt(
        is_first_turn=is_first_turn,
        catalog_context=catalog_context,
    )

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

    prompt = build_intent_extraction_prompt(
        formatted_user_history=formatted_user_history,
        formatted_history=formatted_history,
        user_signal_flags=user_signal_flags,
    )

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
    *,
    resource_options: dict[str, Any] | None = None,
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
    resource_options = resource_options or {"lxc_os_images": [], "vm_operating_systems": []}

    plan_schema = {
        "summary": "Traditional Chinese summary",
        "workload_profile": "one of: lightweight | moderate | compute-intensive | gpu-required | storage-heavy",
        "application_target": {
            "service_name": "string",
            "service_slug": "template-slug-or-empty",
            "execution_environment": "lxc|vm",
            "environment_reason": "Traditional Chinese short reason",
        },
        "form_prefill": {
            "resource_type": "lxc|vm",
            "hostname": "string",
            "service_template_slug": "lxc-service-template-slug-or-empty",
            "lxc_os_image": "real-lxc-os-image-or-empty",
            "vm_os_choice": "real-vm-os-label-or-empty",
            "vm_template_id": "integer-or-0",
            "cores": "integer",
            "memory_mb": "integer",
            "disk_gb": "integer",
            "username": "string-or-empty",
            "reason": "Traditional Chinese short application reason",
        },
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

    prompt = build_ai_plan_prompt(
        user_context=user_context,
        node_capacity_summary=summarize_device_nodes(nodes),
        prompt_bundle=prompt_bundle,
        resource_options=resource_options,
        plan_schema=plan_schema,
    )

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
    *,
    resource_options: dict[str, Any] | None = None,
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
    recommended_templates = recommended_templates[:1]
    recommended_slugs = {item["slug"] for item in recommended_templates}
    possible_needed_templates = [
        item for item in possible_needed_templates if item["slug"] not in recommended_slugs
    ]
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

    application_target = _build_application_target(
        ai_result=ai_result,
        request=request,
        machines=machines,
        recommended_templates=recommended_templates,
    )
    form_prefill = _build_form_prefill(
        ai_result=ai_result,
        request=request,
        machines=machines,
        recommended_templates=recommended_templates,
        resource_options=resource_options or {"lxc_os_images": [], "vm_operating_systems": []},
    )

    final_plan = {
        "summary": computed_summary,
        "application_target": application_target,
        "form_prefill": form_prefill,
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
    default_disk_gb = _safe_int(default_resources.get("hdd"), MIN_LXC_DISK_GB)

    cpu_value = machine.get("cpu")
    memory_value = machine.get("memory_mb")
    disk_value = machine.get("disk_gb")
    gpu_value = machine.get("gpu")
    ai_deployment_type = str(machine.get("deployment_type") or "").strip().lower()
    requested_gpu = max(_safe_int(gpu_value, 1 if request_requires_gpu else 0), 0)
    if request_needs_windows or requested_gpu >= 1:
        deployment_type = "vm"
    else:
        deployment_type = "vm" if ai_deployment_type == "vm" else "lxc"
    min_disk_gb = MIN_VM_DISK_GB if deployment_type == "vm" else 2

    # Allow AI to decide CPU/RAM/Disk, using 1/256/2 as absolute minimums, relying on default if missing.
    cpu = max(_safe_int(cpu_value, default_cpu), 1)
    memory_mb = max(_safe_int(memory_value, default_ram_mb), 256)
    disk_gb = max(_safe_int(disk_value, max(default_disk_gb, min_disk_gb)), min_disk_gb)

    # Let AI decide GPU natively based on its system prompt judgment.
    # Default fallback to 1 only if user globally checked requires_gpu and AI omitted the key.
    fallback_gpu = 1 if request_requires_gpu else 0
    if gpu_value is not None:
        gpu = max(_safe_int(gpu_value, fallback_gpu), 0)
    else:
        gpu = fallback_gpu

    ai_deployment_type = str(machine.get("deployment_type") or "").strip().lower()
    requested_windows = request_needs_windows
    
    # Keep explicit Windows/GPU requests on VM; otherwise trust the model's deployment type.
    if requested_windows or gpu >= 1:
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


def _build_application_target(
    *,
    ai_result: dict[str, Any],
    request: RecommendationRequest,
    machines: list[dict[str, Any]],
    recommended_templates: list[dict[str, Any]],
) -> dict[str, Any]:
    raw = dict(ai_result.get("application_target") or {})
    primary_machine = machines[0] if machines else {}
    primary_template = recommended_templates[0] if recommended_templates else {}

    service_slug = (
        str(raw.get("service_slug") or "").strip().lower()
        or str(primary_template.get("slug") or "").strip().lower()
        or str(primary_machine.get("template_slug") or "").strip().lower()
    )
    service_name = (
        str(raw.get("service_name") or "").strip()
        or str(primary_template.get("name") or "").strip()
        or service_slug
        or request.goal.strip()[:60]
        or "未指定服務"
    )
    execution_environment = (
        str(raw.get("execution_environment") or "").strip().lower()
        or str(primary_machine.get("deployment_type") or "").strip().lower()
        or ("vm" if request.needs_windows else "lxc")
    )
    if execution_environment not in {"lxc", "vm"}:
        execution_environment = "vm" if request.needs_windows else "lxc"

    environment_reason = str(raw.get("environment_reason") or "").strip()
    if not environment_reason:
        if execution_environment == "vm":
            environment_reason = "AI 判斷此需求較適合完整作業系統或圖形化環境，因此採用 VM。"
        else:
            environment_reason = "AI 判斷此需求可直接使用服務模板快速部署，因此優先採用 LXC。"

    return {
        "service_name": service_name or "未指定服務",
        "service_slug": service_slug,
        "execution_environment": execution_environment,
        "environment_reason": environment_reason,
    }


def _build_form_prefill(
    *,
    ai_result: dict[str, Any],
    request: RecommendationRequest,
    machines: list[dict[str, Any]],
    recommended_templates: list[dict[str, Any]],
    resource_options: dict[str, Any],
) -> dict[str, Any]:
    raw = dict(ai_result.get("form_prefill") or {})
    primary_machine = machines[0] if machines else {}
    primary_template = recommended_templates[0] if recommended_templates else {}

    resource_type = (
        str(raw.get("resource_type") or "").strip().lower()
        or str(primary_machine.get("deployment_type") or "").strip().lower()
        or ("vm" if request.needs_windows else "lxc")
    )
    if resource_type not in {"lxc", "vm"}:
        resource_type = "vm" if request.needs_windows else "lxc"

    service_template_slug = (
        str(raw.get("service_template_slug") or raw.get("lxc_template_slug") or "").strip().lower()
        or str(primary_machine.get("template_slug") or "").strip().lower()
        or str(primary_template.get("slug") or "").strip().lower()
    )
    hostname = str(raw.get("hostname") or "").strip() or str(primary_machine.get("name") or "").strip()
    hostname = hostname.lower().replace("_", "-").replace(" ", "-")
    hostname = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in hostname).strip("-")[:63] or (
        f"{service_template_slug}-node"[:63] if service_template_slug else "ai-generated-host"
    )

    def _safe_int_like(value: Any, default: int, minimum: int | None = None) -> int:
        """
        Parse ints from possibly noisy AI / user values like "2 vCPU" or "4GB".
        Falls back to `default` and enforces an optional `minimum`.
        """
        parsed: int
        try:
            if value is None or value == "":
                raise ValueError
            if isinstance(value, str):
                digits = "".join(ch for ch in value if ch.isdigit())
                if digits:
                    parsed = int(digits)
                else:
                    parsed = int(value)
            else:
                parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        if minimum is not None and parsed < minimum:
            parsed = minimum
        return parsed

    lxc_os_images = list(resource_options.get("lxc_os_images") or [])
    vm_operating_systems = list(resource_options.get("vm_operating_systems") or [])
    vm_options_by_id = {
        int(item.get("template_id") or 0): item
        for item in vm_operating_systems
        if int(item.get("template_id") or 0) > 0
    }

    cores = _safe_int_like(raw.get("cores") or primary_machine.get("cpu"), default=2, minimum=2)
    memory_mb = _safe_int_like(raw.get("memory_mb") or primary_machine.get("memory_mb"), default=2048, minimum=2048)
    disk_default = MIN_VM_DISK_GB if resource_type == "vm" else MIN_LXC_DISK_GB
    disk_gb = _safe_int_like(
        raw.get("disk_gb") or primary_machine.get("disk_gb"),
        default=disk_default,
        minimum=disk_default,
    )
    vm_template_id = _safe_int_like(raw.get("vm_template_id"), default=0, minimum=0)
    vm_os_choice = str(raw.get("vm_os_choice") or raw.get("os_environment") or "").strip()
    if vm_template_id and not vm_os_choice:
        vm_os_choice = str(vm_options_by_id.get(vm_template_id, {}).get("label") or "").strip()
    if not vm_os_choice and resource_type == "vm":
        vm_os_choice = "Windows" if request.needs_windows else "Linux"
    lxc_os_image = str(raw.get("lxc_os_image") or "").strip()
    if lxc_os_image and not any(str(item.get("value") or "") == lxc_os_image for item in lxc_os_images):
        lxc_os_image = ""
    username = str(raw.get("username") or "").strip()
    if resource_type == "vm" and not username:
        username = "student"

    service_label = str(primary_template.get("name") or service_template_slug or request.goal.strip()[:40] or "目標服務").strip()
    reason = _build_submission_reason(
        request=request,
        service_label=service_label,
        resource_type=resource_type,
        cores=cores,
        memory_mb=memory_mb,
        disk_gb=disk_gb,
    )

    return {
        "resource_type": resource_type,
        "hostname": hostname,
        "service_template_slug": service_template_slug if resource_type == "lxc" else "",
        "lxc_template_slug": service_template_slug if resource_type == "lxc" else "",
        "lxc_os_image": lxc_os_image if resource_type == "lxc" else "",
        "vm_os_choice": vm_os_choice if resource_type == "vm" else "",
        "vm_template_id": vm_template_id if resource_type == "vm" else 0,
        "os_environment": vm_os_choice.lower() if resource_type == "vm" else "linux",
        "cores": cores,
        "memory_mb": memory_mb,
        "disk_gb": disk_gb,
        "username": username,
        "reason": reason,
    }


def _build_submission_reason(
    *,
    request: RecommendationRequest,
    service_label: str,
    resource_type: str,
    cores: int,
    memory_mb: int,
    disk_gb: int,
) -> str:
    usage_prefix = (
        "課程作業" if request.course_context == "coursework"
        else "教學使用" if request.course_context == "teaching"
        else "研究用途"
    )
    sharing_text = "個人使用" if request.sharing_scope == "personal" else "小組使用"
    deployment_label = "LXC" if resource_type == "lxc" else "VM"
    ram_gb = memory_mb / 1024
    return (
        f"{sharing_text}{usage_prefix}申請，規劃以 {deployment_label} 部署 {service_label}，"
        f"目前申請 {cores} vCPU、{ram_gb:.1f} GB RAM、{disk_gb} GB 磁碟，"
        "配置以滿足現階段基本使用需求為主。"
    )


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
