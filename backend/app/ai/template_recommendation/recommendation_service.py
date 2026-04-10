from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from fastapi import HTTPException

from app.ai.template_recommendation.catalog_service import (
    TemplateCatalog,
    build_catalog_prompt_bundle,
    catalog_lookup,
)
from app.infrastructure.ai.template_recommendation import client
from app.ai.template_recommendation.config import settings
from app.ai.template_recommendation.node_service import summarize_device_nodes
from app.ai.template_recommendation.prompt import (
    build_ai_plan_prompt,
    build_intent_extraction_prompt,
)
from app.ai.template_recommendation.schemas import (
    ChatMessage,
    ChatRequest,
    DeviceNode,
    ExtractedIntent,
    RecommendationRequest,
)


def _extract_user_signal_flags(messages: list[ChatMessage]) -> dict[str, bool]:
    user_text = "\n".join(
        str(message.content)
        for message in messages
        if str(message.role).strip().lower() == "user"
    ).lower()

    def _contains_any(keywords: tuple[str, ...]) -> bool:
        return any(keyword in user_text for keyword in keywords)

    return {
        "needs_windows": _contains_any(("windows", "win11", "win10", "rdp", "remote desktop", "gui")),
        "requires_gpu": _contains_any(("gpu", "cuda", "pytorch", "tensorflow", "llm", "stable diffusion", "comfyui", "ai")),
        "needs_database": _contains_any(("database", "db", "mysql", "postgres", "postgresql", "mariadb", "mongodb", "redis", "sql")),
        "needs_public_web": _contains_any(("public", "internet", "external", "domain")),
    }


def _apply_thinking_control(payload: dict[str, Any]) -> dict[str, Any]:
    payload["chat_template_kwargs"] = {
        **dict(payload.get("chat_template_kwargs") or {}),
        "enable_thinking": settings.vllm_enable_thinking,
    }
    return payload


def _safe_int(value: Any, default: int, minimum: int) -> int:
    try:
        if isinstance(value, str):
            digits = "".join(char for char in value if char.isdigit())
            parsed = int(digits) if digits else int(value)
        else:
            parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, minimum)


def _build_submission_reason(
    *,
    request: RecommendationRequest,
    resource_type: str,
    service_name: str,
    cores: int,
    memory_mb: int,
    disk_gb: int,
) -> str:
    usage_label = {
        "coursework": "課程作業",
        "teaching": "教學服務",
        "research": "研究用途",
    }.get(request.course_context, "一般用途")
    scope_label = "個人使用" if request.sharing_scope == "personal" else "共享使用"
    env_label = "LXC" if resource_type == "lxc" else "VM"
    return (
        f"申請 {env_label} 執行 {service_name}，供{scope_label}的{usage_label}使用，"
        f"配置 {cores} vCPU、{memory_mb} MB RAM、{disk_gb} GB Disk，"
        "以符合目前功能需求並避免資源浪費。"
    )


async def extract_intent_from_chat(request: ChatRequest) -> ExtractedIntent:
    model_name = settings.resolved_vllm_model_name
    if not model_name:
        raise HTTPException(
            status_code=503,
            detail="AI model binding is missing in config/system-ai.json.",
        )

    recent_messages = request.messages[-10:]
    user_messages: list[str] = []
    full_chat_history: list[str] = []

    for message in recent_messages:
        normalized_role = str(message.role).strip().lower()
        if normalized_role == "user":
            user_messages.append(f"User: {message.content}")
            full_chat_history.append(f"User: {message.content}")
        elif normalized_role == "assistant":
            full_chat_history.append(f"Assistant: {message.content}")

    prompt = build_intent_extraction_prompt(
        formatted_user_history="\n\n".join(user_messages) if user_messages else "(No user messages)",
        formatted_history="\n\n".join(full_chat_history) if full_chat_history else "(No conversation history)",
        user_signal_flags=_extract_user_signal_flags(recent_messages),
    )
    payload = _apply_thinking_control(
        {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
    )

    try:
        data = await client.create_chat_completion(payload)
        return ExtractedIntent(**json.loads(data["choices"][0]["message"]["content"]))
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
    model_name = settings.resolved_vllm_model_name
    if not model_name:
        raise HTTPException(
            status_code=503,
            detail="AI model binding is missing in config/system-ai.json.",
        )

    del chat_history

    prompt_bundle = build_catalog_prompt_bundle(
        template_catalog,
        request.goal,
        request.top_k,
        needs_public_web=request.needs_public_web,
        needs_database=request.needs_database,
    )
    user_context = {
        "goal": request.goal,
        "role": request.role,
        "course_context": request.course_context,
        "sharing_scope": request.sharing_scope,
        "expected_users": request.expected_users,
        "budget_mode": request.budget_mode,
        "needs_public_web": request.needs_public_web,
        "needs_database": request.needs_database,
        "requires_gpu": request.requires_gpu,
        "needs_windows": request.needs_windows,
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
            {"slug": "template-slug", "name": "template-name", "why": "Traditional Chinese reason"}
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
                "gpu": "integer",
                "assigned_node": "node-name-or-null",
                "why": "Traditional Chinese reason",
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
        "upgrade_when": "Traditional Chinese upgrade timing with measurable thresholds",
    }
    payload = _apply_thinking_control(
        {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": build_ai_plan_prompt(
                        user_context=user_context,
                        node_capacity_summary=summarize_device_nodes(nodes),
                        prompt_bundle=prompt_bundle,
                        resource_options=resource_options,
                        plan_schema=plan_schema,
                    ),
                }
            ],
            "max_tokens": settings.vllm_max_tokens,
            "temperature": settings.vllm_temperature,
            "top_p": settings.vllm_top_p,
            "top_k": settings.vllm_top_k,
            "min_p": settings.vllm_min_p,
            "presence_penalty": settings.vllm_presence_penalty,
            "repetition_penalty": settings.vllm_repetition_penalty,
            "response_format": {"type": "json_object"},
        }
    )

    try:
        started_at = perf_counter()
        data = await client.create_chat_completion(payload)
        elapsed_seconds = max(perf_counter() - started_at, 0.0)
        usage = data.get("usage") or {}
        completion_tokens = int(usage.get("completion_tokens") or 0)
        metrics = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": completion_tokens,
            "total_tokens": int(usage.get("total_tokens") or 0),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "tokens_per_second": round((completion_tokens / elapsed_seconds) if elapsed_seconds > 0 else 0.0, 2),
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
    resource_options = resource_options or {"lxc_os_images": [], "vm_operating_systems": []}
    lxc_os_images = list(resource_options.get("lxc_os_images") or [])
    vm_operating_systems = list(resource_options.get("vm_operating_systems") or [])

    recommended_templates: list[dict[str, Any]] = []
    for item in list(ai_result.get("recommended_templates") or []):
        slug = str(item.get("slug") or "").strip().lower()
        template = lookup.get(slug)
        if not template:
            continue
        recommended_templates.append(
            {
                "slug": template.slug,
                "name": template.name,
                "why": str(item.get("why") or "AI 依需求推薦此模板。").strip(),
            }
        )

    possible_needed_templates: list[dict[str, Any]] = []
    for item in list(ai_result.get("possible_needed_templates") or []):
        slug = str(item.get("slug") or "").strip().lower()
        template = lookup.get(slug)
        if not template or any(existing["slug"] == template.slug for existing in recommended_templates):
            continue
        possible_needed_templates.append(
            {
                "slug": template.slug,
                "name": template.name,
                "why": str(item.get("why") or "AI 判斷可能需要此輔助模板。").strip(),
            }
        )

    machines: list[dict[str, Any]] = []
    for machine in list(ai_result.get("machines") or []):
        slug = str(machine.get("template_slug") or "").strip().lower()
        template = lookup.get(slug)
        if not template:
            continue

        install_methods = template.raw.get("install_methods") or []
        default_resources = dict((install_methods[0].get("resources") or {})) if install_methods else {}
        cpu = _safe_int(machine.get("cpu"), int(default_resources.get("cpu") or 2), 1)
        memory_mb = _safe_int(machine.get("memory_mb"), int(default_resources.get("ram") or 2048), 256)
        disk_gb = _safe_int(machine.get("disk_gb"), int(default_resources.get("hdd") or 10), 2)
        gpu = _safe_int(machine.get("gpu"), 1 if request.requires_gpu else 0, 0)
        deployment_type = str(machine.get("deployment_type") or "").strip().lower()
        if deployment_type not in {"lxc", "vm"}:
            deployment_type = "vm" if (request.needs_windows or gpu > 0) else "lxc"

        machines.append(
            {
                "name": str(machine.get("name") or f"{template.slug}-node").strip(),
                "purpose": str(machine.get("purpose") or "主要服務").strip(),
                "template_slug": template.slug,
                "deployment_type": deployment_type,
                "cpu": cpu,
                "memory_mb": memory_mb,
                "disk_gb": disk_gb,
                "gpu": gpu,
                "assigned_node": machine.get("assigned_node"),
                "why": str(machine.get("why") or "AI 依需求與目前節點容量安排此部署單位。").strip(),
            }
        )

    primary_machine = machines[0] if machines else {}
    primary_template = recommended_templates[0] if recommended_templates else {}
    resource_type = str(
        ai_result.get("form_prefill", {}).get("resource_type")
        or primary_machine.get("deployment_type")
        or ("vm" if request.needs_windows else "lxc")
    ).lower()
    if resource_type not in {"lxc", "vm"}:
        resource_type = "vm" if request.needs_windows else "lxc"

    hostname_seed = str(
        ai_result.get("form_prefill", {}).get("hostname")
        or primary_machine.get("name")
        or primary_template.get("slug")
        or "ai-generated-host"
    ).lower()
    hostname = "".join(char if (char.isalnum() or char == "-") else "-" for char in hostname_seed.replace("_", "-")).strip("-")[:63]
    if not hostname:
        hostname = "ai-generated-host"

    service_template_slug = str(
        ai_result.get("form_prefill", {}).get("service_template_slug")
        or primary_template.get("slug")
        or primary_machine.get("template_slug")
        or ""
    ).strip().lower()

    selected_lxc_image = ""
    if resource_type == "lxc" and lxc_os_images:
        requested_image = str(ai_result.get("form_prefill", {}).get("lxc_os_image") or "").strip()
        selected_lxc_image = next(
            (item["value"] for item in lxc_os_images if item["value"] == requested_image),
            lxc_os_images[0]["value"],
        )

    selected_vm_template_id = 0
    selected_vm_os = ""
    if resource_type == "vm" and vm_operating_systems:
        requested_vm_template_id = _safe_int(ai_result.get("form_prefill", {}).get("vm_template_id"), 0, 0)
        selected_vm = next(
            (item for item in vm_operating_systems if int(item.get("template_id") or 0) == requested_vm_template_id),
            vm_operating_systems[0],
        )
        selected_vm_template_id = int(selected_vm.get("template_id") or 0)
        selected_vm_os = str(selected_vm.get("label") or "").strip()

    cores = _safe_int(ai_result.get("form_prefill", {}).get("cores") or primary_machine.get("cpu"), 2, 1)
    memory_mb = _safe_int(ai_result.get("form_prefill", {}).get("memory_mb") or primary_machine.get("memory_mb"), 2048, 512)
    disk_gb = _safe_int(ai_result.get("form_prefill", {}).get("disk_gb") or primary_machine.get("disk_gb"), 10, 8)
    username = ""
    if resource_type == "vm":
        username = str(ai_result.get("form_prefill", {}).get("username") or "student").strip() or "student"

    service_name = str(
        ai_result.get("application_target", {}).get("service_name")
        or primary_template.get("name")
        or request.goal[:40]
    ).strip()

    form_prefill = {
        "resource_type": resource_type,
        "hostname": hostname,
        "service_template_slug": service_template_slug if resource_type == "lxc" else "",
        "lxc_os_image": selected_lxc_image if resource_type == "lxc" else "",
        "vm_os_choice": selected_vm_os if resource_type == "vm" else "",
        "vm_template_id": selected_vm_template_id if resource_type == "vm" else 0,
        "cores": cores,
        "memory_mb": memory_mb,
        "disk_gb": disk_gb,
        "username": username,
        "reason": _build_submission_reason(
            request=request,
            resource_type=resource_type,
            service_name=service_name,
            cores=cores,
            memory_mb=memory_mb,
            disk_gb=disk_gb,
        ),
    }

    return {
        "persona": {
            "role": request.role,
            "course_context": request.course_context,
            "sharing_scope": request.sharing_scope,
            "budget_mode": request.budget_mode,
        },
        "device_profile": summarize_device_nodes(nodes),
        "summary": str(ai_result.get("summary") or "").strip(),
        "workload_profile": str(ai_result.get("workload_profile") or "ai-planned").strip(),
        "rule_basis": {
            "reasons": [str(item).strip() for item in list(ai_result.get("decision_factors") or []) if str(item).strip()],
            "capacity_checks": [
                {
                    "machine": machine.get("name"),
                    "assigned_node": machine.get("assigned_node"),
                    "status": "ai-assigned",
                }
                for machine in machines
            ],
        },
        "recommended_path": {
            "fit": "ai-generated plan",
            "why": [item["why"] for item in recommended_templates] or ["AI 依需求與可用設備規劃推薦路徑。"],
            "upgrade_when": str(ai_result.get("upgrade_when") or "").strip(),
        },
        "final_plan": {
            "summary": str(ai_result.get("summary") or "").strip(),
            "application_target": {
                "service_name": service_name,
                "service_slug": service_template_slug,
                "execution_environment": resource_type,
                "environment_reason": str(
                    ai_result.get("application_target", {}).get("environment_reason")
                    or ("使用 VM 以符合作業系統或環境需求。" if resource_type == "vm" else "使用 LXC 以提供較精簡的服務部署方式。")
                ).strip(),
            },
            "form_prefill": form_prefill,
            "machines": machines,
            "recommended_templates": recommended_templates,
            "possible_needed_templates": possible_needed_templates[:3],
            "overall_config": {
                "deployment_strategy": str(ai_result.get("overall_config", {}).get("deployment_strategy") or "AI 依需求、模板與目前節點容量整理部署策略。").strip(),
                "machine_count": len(machines),
                "total_cpu": sum(int(machine.get("cpu") or 0) for machine in machines),
                "total_memory_mb": sum(int(machine.get("memory_mb") or 0) for machine in machines),
                "total_disk_gb": sum(int(machine.get("disk_gb") or 0) for machine in machines),
            },
        },
    }
