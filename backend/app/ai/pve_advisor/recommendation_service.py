from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil, floor
from time import perf_counter
from typing import Any

from sqlmodel import Session, func, select

from app.ai.pve_advisor.client import client
from app.ai.pve_advisor.config import settings
from app.ai.pve_advisor.prompt import (
    build_advisor_system_prompt,
    build_advisor_user_prompt,
)
from app.ai.pve_advisor.schemas import (
    AiMetrics,
    AuditSignalSnapshot,
    BackendTrafficSnapshot,
    NodeCapacity,
    NodeSnapshot,
    PlacementAdvisorResponse,
    PlacementDecision,
    PlacementPlan,
    PlacementRequest,
    ResourceSnapshot,
    SuggestedAction,
)
from app.models import AuditAction, AuditLog, VMRequest, VMRequestStatus
from app.services import proxmox_service


GIB = 1024**3
MIB = 1024**2


class _ClusterCacheEntry:
    def __init__(
        self,
        cached_at: float,
        nodes: list[NodeSnapshot],
        resources: list[ResourceSnapshot],
    ) -> None:
        self.cached_at = cached_at
        self.nodes = nodes
        self.resources = resources


_cluster_cache: _ClusterCacheEntry | None = None
_cluster_cache_lock = threading.Lock()


async def generate_recommendation(
    *,
    session: Session,
    request: PlacementRequest,
) -> PlacementAdvisorResponse:
    nodes, resources = _load_cluster_state()
    backend_traffic = _load_backend_traffic_snapshot(session=session)
    audit_signals = _load_audit_signal_snapshot(session=session)
    node_capacities = _build_node_capacities(nodes=nodes, resources=resources)
    placement = _build_placement_plan(
        request=request,
        node_capacities=node_capacities,
    )
    fallback_reply = _build_fallback_reply(
        request=request,
        placement=placement,
        backend_traffic=backend_traffic,
        audit_signals=audit_signals,
    )

    suggested_action = None
    if placement.recommended_node:
        suggested_action = SuggestedAction(
            node=placement.recommended_node,
            resource_type=request.resource_type,
            instance_count=request.instance_count,
        )

    if not settings.vllm_model_name:
        return PlacementAdvisorResponse(
            reply=fallback_reply,
            ai_used=False,
            warning="VLLM_MODEL_NAME is not configured, so the service returned a rule-based answer.",
            request=request,
            placement=placement,
            suggested_action=suggested_action,
            backend_traffic=backend_traffic,
            audit_signals=audit_signals,
            node_capacities=node_capacities,
        )

    try:
        reply, metrics = await _generate_ai_reply(
            request=request,
            placement=placement,
            backend_traffic=backend_traffic,
            audit_signals=audit_signals,
            node_capacities=node_capacities,
        )
        return PlacementAdvisorResponse(
            reply=reply,
            ai_used=True,
            model=settings.vllm_model_name,
            ai_metrics=metrics,
            request=request,
            placement=placement,
            suggested_action=suggested_action,
            backend_traffic=backend_traffic,
            audit_signals=audit_signals,
            node_capacities=node_capacities,
        )
    except Exception as exc:
        return PlacementAdvisorResponse(
            reply=fallback_reply,
            ai_used=False,
            warning=f"AI call failed, so the service returned a rule-based answer: {exc}",
            request=request,
            placement=placement,
            suggested_action=suggested_action,
            backend_traffic=backend_traffic,
            audit_signals=audit_signals,
            node_capacities=node_capacities,
        )


async def _generate_ai_reply(
    *,
    request: PlacementRequest,
    placement: PlacementPlan,
    backend_traffic: BackendTrafficSnapshot,
    audit_signals: AuditSignalSnapshot,
    node_capacities: list[NodeCapacity],
) -> tuple[str, AiMetrics]:
    payload = _apply_thinking_control(
        {
            "model": settings.vllm_model_name,
            "messages": [
                {"role": "system", "content": build_advisor_system_prompt()},
                {
                    "role": "user",
                    "content": build_advisor_user_prompt(
                        request=request.model_dump(),
                        placement=placement.model_dump(),
                        backend_traffic=backend_traffic.model_dump(),
                        audit_signals=audit_signals.model_dump(),
                        node_capacities=[item.model_dump() for item in node_capacities],
                    ),
                },
            ],
            "max_tokens": settings.vllm_max_tokens,
            "temperature": settings.vllm_temperature,
            "top_p": settings.vllm_top_p,
            "top_k": settings.vllm_top_k,
            "min_p": settings.vllm_min_p,
            "repetition_penalty": settings.vllm_repetition_penalty,
        }
    )

    started_at = perf_counter()
    data = await client.create_chat_completion(payload)
    elapsed_seconds = max(perf_counter() - started_at, 0.0)
    usage = data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    reply = _strip_think_tags(str(data["choices"][0]["message"]["content"] or ""))
    metrics = AiMetrics(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        elapsed_seconds=round(elapsed_seconds, 3),
        tokens_per_second=round(
            (completion_tokens / elapsed_seconds) if elapsed_seconds > 0 else 0.0,
            2,
        ),
    )
    return reply, metrics


def _strip_think_tags(text: str) -> str:
    marker = "</think>"
    idx = text.find(marker)
    if idx != -1:
        return text[idx + len(marker) :].strip()
    return text.strip()


def _apply_thinking_control(payload: dict[str, Any]) -> dict[str, Any]:
    payload["chat_template_kwargs"] = {
        **dict(payload.get("chat_template_kwargs") or {}),
        "enable_thinking": settings.vllm_enable_thinking,
    }
    return payload


def _load_cluster_state() -> tuple[list[NodeSnapshot], list[ResourceSnapshot]]:
    cached = _get_cached_cluster_state()
    if cached is not None:
        return cached.nodes, cached.resources

    gpu_map = settings.parsed_backend_node_gpu_map
    nodes = [
        NodeSnapshot(
            node=str(item.get("node") or "unknown"),
            status=str(item.get("status") or "unknown"),
            cpu_ratio=float(item.get("cpu") or 0.0),
            maxcpu=int(item.get("maxcpu") or 0),
            mem_bytes=int(item.get("mem") or 0),
            maxmem_bytes=int(item.get("maxmem") or 0),
            disk_bytes=int(item.get("disk") or 0),
            maxdisk_bytes=int(item.get("maxdisk") or 0),
            uptime=_optional_int(item.get("uptime")),
            gpu_count=gpu_map.get(str(item.get("node") or "unknown"), 0),
        )
        for item in proxmox_service.list_nodes()
    ]
    resources = [
        ResourceSnapshot(
            vmid=int(item.get("vmid") or 0),
            name=str(item.get("name") or ""),
            resource_type=str(item.get("type") or "unknown"),
            node=str(item.get("node") or "unknown"),
            status=str(item.get("status") or "unknown"),
            cpu_ratio=float(item.get("cpu") or 0.0),
            maxcpu=int(item.get("maxcpu") or 0),
            mem_bytes=int(item.get("mem") or 0),
            maxmem_bytes=int(item.get("maxmem") or 0),
            disk_bytes=int(item.get("disk") or 0),
            maxdisk_bytes=int(item.get("maxdisk") or 0),
            uptime=_optional_int(item.get("uptime")),
        )
        for item in proxmox_service.list_all_resources()
        if item.get("template") != 1
    ]
    _set_cached_cluster_state(nodes=nodes, resources=resources)
    return nodes, resources


def _load_backend_traffic_snapshot(*, session: Session) -> BackendTrafficSnapshot:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=settings.backend_traffic_window_minutes)

    recent_requests = list(
        session.exec(
            select(VMRequest)
            .order_by(VMRequest.created_at.desc())  # type: ignore[union-attr]
            .limit(settings.backend_traffic_sample_limit)
        ).all()
    )
    pending_total = session.exec(
        select(func.count())
        .select_from(VMRequest)
        .where(VMRequest.status == VMRequestStatus.pending)
    ).one()
    approved_total = session.exec(
        select(func.count())
        .select_from(VMRequest)
        .where(VMRequest.status == VMRequestStatus.approved)
    ).one()

    submitted = 0
    requested_cpu = 0
    requested_memory_mb = 0
    requested_disk_gb = 0
    for item in recent_requests:
        if item.created_at and item.created_at >= window_start:
            submitted += 1
        requested_cpu += max(int(item.cores or 0), 0)
        requested_memory_mb += max(int(item.memory or 0), 0)
        requested_disk_gb += max(int(item.disk_size or item.rootfs_size or 0), 0)

    return BackendTrafficSnapshot(
        sample_size=len(recent_requests),
        window_minutes=settings.backend_traffic_window_minutes,
        submitted_in_window=submitted,
        pending_total=int(pending_total or 0),
        approved_total=int(approved_total or 0),
        requested_cpu_cores_total=requested_cpu,
        requested_memory_mb_total=requested_memory_mb,
        requested_disk_gb_total=requested_disk_gb,
    )


def _load_audit_signal_snapshot(*, session: Session) -> AuditSignalSnapshot:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=settings.audit_log_window_minutes)
    rows = list(
        session.exec(
            select(AuditLog)
            .where(AuditLog.created_at >= window_start)  # type: ignore[operator]
            .order_by(AuditLog.created_at.desc())
            .limit(settings.audit_log_sample_limit)
        ).all()
    )
    counts = Counter(
        str(row.action.value if isinstance(row.action, AuditAction) else row.action)
        for row in rows
    )
    return AuditSignalSnapshot(
        sample_size=len(rows),
        window_minutes=settings.audit_log_window_minutes,
        recent_total=len(rows),
        create_events=counts["vm_create"] + counts["lxc_create"],
        start_events=counts["resource_start"],
        stop_events=counts["resource_stop"]
        + counts["resource_shutdown"]
        + counts["resource_reset"],
        delete_events=counts["resource_delete"],
        review_events=counts["vm_request_review"],
    )


def _build_node_capacities(
    *,
    nodes: list[NodeSnapshot],
    resources: list[ResourceSnapshot],
) -> list[NodeCapacity]:
    running_counter = Counter(
        resource.node
        for resource in resources
        if str(resource.status).lower() == "running"
    )
    capacities: list[NodeCapacity] = []
    for node in nodes:
        running_resources = running_counter.get(node.node, 0)
        guest_soft_limit = _guest_soft_limit(node.maxcpu)
        guest_pressure_ratio = _guest_pressure_ratio(running_resources, node.maxcpu)
        raw_available_cpu = _raw_available_cpu(node)
        raw_available_memory = _raw_available_bytes(node.mem_bytes, node.maxmem_bytes)
        raw_available_disk = _raw_available_bytes(node.disk_bytes, node.maxdisk_bytes)
        allocatable_cpu = _safe_available_float(raw_available_cpu, node.maxcpu)
        allocatable_memory = _safe_available_int(raw_available_memory, node.maxmem_bytes)
        allocatable_disk = _safe_available_int(raw_available_disk, node.maxdisk_bytes)
        guest_overloaded = guest_pressure_ratio >= settings.guest_pressure_threshold
        capacities.append(
            NodeCapacity(
                node=node.node,
                status=node.status,
                gpu_count=node.gpu_count,
                running_resources=running_resources,
                guest_soft_limit=guest_soft_limit,
                guest_pressure_ratio=guest_pressure_ratio,
                guest_overloaded=guest_overloaded,
                candidate=(
                    node.status == "online"
                    and allocatable_cpu > 0
                    and allocatable_memory > 0
                    and allocatable_disk > 0
                    and not guest_overloaded
                ),
                cpu_ratio=node.cpu_ratio,
                memory_ratio=_ratio(node.mem_bytes, node.maxmem_bytes),
                disk_ratio=_ratio(node.disk_bytes, node.maxdisk_bytes),
                total_cpu_cores=float(node.maxcpu),
                allocatable_cpu_cores=allocatable_cpu,
                total_memory_bytes=node.maxmem_bytes,
                allocatable_memory_bytes=allocatable_memory,
                total_disk_bytes=node.maxdisk_bytes,
                allocatable_disk_bytes=allocatable_disk,
            )
        )
    return sorted(capacities, key=lambda item: item.node)


def _build_placement_plan(
    *,
    request: PlacementRequest,
    node_capacities: list[NodeCapacity],
) -> PlacementPlan:
    working_nodes = [item.model_copy(deep=True) for item in node_capacities]
    req_disk = request.disk_gb * GIB
    effective_cpu = _effective_cpu_cores(request)
    effective_memory = _effective_memory_bytes(request)
    placements: dict[str, int] = {item.node: 0 for item in working_nodes}
    remaining = request.instance_count

    while remaining > 0:
        candidates = [
            item
            for item in working_nodes
            if item.candidate
            and _can_fit(
                item,
                cores=effective_cpu,
                memory_bytes=effective_memory,
                disk_bytes=req_disk,
                gpu_required=request.gpu_required,
            )
        ]
        if not candidates:
            break

        chosen = _choose_node(
            nodes=candidates,
            placements=placements,
            cores=effective_cpu,
            memory_bytes=effective_memory,
            disk_bytes=req_disk,
        )
        placements[chosen.node] += 1
        chosen.allocatable_cpu_cores = max(
            chosen.allocatable_cpu_cores - effective_cpu,
            0.0,
        )
        chosen.allocatable_memory_bytes = max(
            chosen.allocatable_memory_bytes - effective_memory,
            0,
        )
        chosen.allocatable_disk_bytes = max(
            chosen.allocatable_disk_bytes - req_disk,
            0,
        )
        chosen.running_resources += 1
        chosen.guest_pressure_ratio = _guest_pressure_ratio(
            chosen.running_resources,
            int(chosen.total_cpu_cores),
        )
        chosen.guest_overloaded = (
            chosen.guest_pressure_ratio >= settings.guest_pressure_threshold
        )
        chosen.candidate = (
            chosen.status == "online"
            and chosen.allocatable_cpu_cores > 0
            and chosen.allocatable_memory_bytes > 0
            and chosen.allocatable_disk_bytes > 0
            and not chosen.guest_overloaded
        )
        remaining -= 1

    assigned = request.instance_count - remaining
    placement_decisions = [
        PlacementDecision(
            node=item.node,
            instance_count=placements[item.node],
            cpu_cores_reserved=round(placements[item.node] * effective_cpu, 2),
            memory_bytes_reserved=placements[item.node] * effective_memory,
            disk_bytes_reserved=placements[item.node] * req_disk,
            remaining_cpu_cores=round(item.allocatable_cpu_cores, 2),
            remaining_memory_bytes=item.allocatable_memory_bytes,
            remaining_disk_bytes=item.allocatable_disk_bytes,
        )
        for item in working_nodes
        if placements[item.node] > 0
    ]
    placement_decisions.sort(key=lambda item: (-item.instance_count, item.node))

    recommended_node = placement_decisions[0].node if placement_decisions else None
    warnings = _build_warnings(
        node_capacities=node_capacities,
        request=request,
        remaining=remaining,
    )
    rationale = _build_rationale(
        request=request,
        placement_decisions=placement_decisions,
        effective_cpu=effective_cpu,
        effective_memory=effective_memory,
        node_capacities=node_capacities,
    )
    summary = _build_summary_text(
        request=request,
        placement_decisions=placement_decisions,
        assigned=assigned,
        remaining=remaining,
    )

    return PlacementPlan(
        feasible=remaining == 0,
        assigned_instances=assigned,
        unassigned_instances=remaining,
        effective_cpu_cores_per_instance=round(effective_cpu, 2),
        effective_memory_bytes_per_instance=effective_memory,
        recommended_node=recommended_node,
        summary=summary,
        rationale=rationale,
        warnings=warnings,
        placements=placement_decisions,
        candidate_nodes=working_nodes,
    )


def _build_fallback_reply(
    *,
    request: PlacementRequest,
    placement: PlacementPlan,
    backend_traffic: BackendTrafficSnapshot,
    audit_signals: AuditSignalSnapshot,
) -> str:
    lines: list[str] = []
    if placement.recommended_node:
        if placement.feasible:
            lines.append(
                f"建議先把 {request.machine_name} 放在 {placement.recommended_node}。"
            )
        else:
            lines.append(
                f"目前最適合的節點是 {placement.recommended_node}，但只能先容納 {placement.assigned_instances} / {request.instance_count} 台。"
            )
    else:
        lines.append(
            f"目前找不到能安全放置 {request.machine_name} 的 PVE 節點。"
        )

    if placement.placements:
        lines.append(
            "建議分配: "
            + ", ".join(f"{item.node} x{item.instance_count}" for item in placement.placements)
            + "。"
        )

    if placement.rationale:
        lines.append(f"主要原因: {placement.rationale[0]}")

    signal_parts: list[str] = []
    if backend_traffic.pending_total >= settings.backend_pending_high_threshold:
        signal_parts.append(
            f"後端目前有 {backend_traffic.pending_total} 筆待審核申請"
        )
    if audit_signals.recent_total >= settings.audit_log_burst_threshold:
        signal_parts.append(
            f"最近 {audit_signals.window_minutes} 分鐘內有 {audit_signals.recent_total} 筆操作紀錄"
        )
    if signal_parts:
        lines.append("風險訊號: " + "，".join(signal_parts) + "。")

    lines.append("這是建議結果，尚未執行實際開機、建立或分配動作。")
    return " ".join(lines)


def _build_warnings(
    *,
    node_capacities: list[NodeCapacity],
    request: PlacementRequest,
    remaining: int,
) -> list[str]:
    warnings: list[str] = []
    overloaded = [item.node for item in node_capacities if item.guest_overloaded]
    if overloaded:
        warnings.append("Guest pressure is already high on: " + ", ".join(overloaded))
    if request.gpu_required > 0 and not any(
        item.gpu_count >= request.gpu_required for item in node_capacities
    ):
        warnings.append(
            f"No node currently exposes at least {request.gpu_required} GPU(s)."
        )
    if remaining > 0:
        warnings.append(
            f"Capacity is insufficient for {remaining} remaining instance(s)."
        )
    return warnings


def _build_rationale(
    *,
    request: PlacementRequest,
    placement_decisions: list[PlacementDecision],
    effective_cpu: float,
    effective_memory: int,
    node_capacities: list[NodeCapacity],
) -> list[str]:
    capacity_map = {item.node: item for item in node_capacities}
    reasons: list[str] = []
    if request.estimated_users_per_instance > 0:
        reasons.append(
            (
                f"依照每台約 {request.estimated_users_per_instance} 位使用者估算，"
                f"單台需求以 {effective_cpu:.1f} vCPU / {effective_memory / GIB:.1f} GiB RAM 計算。"
            )
        )
    for item in placement_decisions:
        baseline = capacity_map.get(item.node)
        if baseline is None:
            continue
        reasons.append(
            (
                f"{item.node} 放入後仍保留約 {item.remaining_cpu_cores:.1f} vCPU、"
                f"{item.remaining_memory_bytes / GIB:.1f} GiB RAM、"
                f"{item.remaining_disk_bytes / GIB:.1f} GiB Disk，"
                f"目前 guest 壓力 {baseline.guest_pressure_ratio:.2f}。"
            )
        )
    return reasons


def _build_summary_text(
    *,
    request: PlacementRequest,
    placement_decisions: list[PlacementDecision],
    assigned: int,
    remaining: int,
) -> str:
    if not placement_decisions:
        return (
            f"{request.machine_name} 目前無法放置，沒有節點同時滿足 CPU、記憶體、磁碟與 GPU 條件。"
        )
    distribution = ", ".join(
        f"{item.node} x{item.instance_count}" for item in placement_decisions
    )
    if remaining == 0:
        return f"{request.machine_name} 可完整放置，建議分配為 {distribution}。"
    return (
        f"{request.machine_name} 只能部分放置，目前可先分配 {assigned} / {request.instance_count} 台，"
        f"建議分配為 {distribution}。"
    )


def _get_cached_cluster_state() -> _ClusterCacheEntry | None:
    with _cluster_cache_lock:
        if _cluster_cache is None:
            return None
        age = time.monotonic() - _cluster_cache.cached_at
        if age > settings.source_cache_ttl_seconds:
            return None
        return _cluster_cache


def _set_cached_cluster_state(
    *,
    nodes: list[NodeSnapshot],
    resources: list[ResourceSnapshot],
) -> None:
    if settings.source_cache_ttl_seconds <= 0:
        return
    with _cluster_cache_lock:
        global _cluster_cache
        _cluster_cache = _ClusterCacheEntry(
            cached_at=time.monotonic(),
            nodes=nodes,
            resources=resources,
        )


def _choose_node(
    *,
    nodes: list[NodeCapacity],
    placements: dict[str, int],
    cores: float,
    memory_bytes: int,
    disk_bytes: int,
) -> NodeCapacity:
    return max(
        nodes,
        key=lambda item: (
            -placements[item.node],
            _fit_count(
                item,
                cores=cores,
                memory_bytes=memory_bytes,
                disk_bytes=disk_bytes,
            ),
            _weighted_headroom_score(
                item,
                cores=cores,
                memory_bytes=memory_bytes,
                disk_bytes=disk_bytes,
            ),
            -item.guest_pressure_ratio,
        ),
    )


def _fit_count(
    node: NodeCapacity,
    *,
    cores: float,
    memory_bytes: int,
    disk_bytes: int,
) -> int:
    cpu_fit = floor(node.allocatable_cpu_cores / float(cores)) if cores > 0 else 0
    memory_fit = (
        floor(node.allocatable_memory_bytes / memory_bytes) if memory_bytes > 0 else 0
    )
    disk_fit = floor(node.allocatable_disk_bytes / disk_bytes) if disk_bytes > 0 else 0
    guest_fit = max(node.guest_soft_limit - node.running_resources, 0)
    return max(min(cpu_fit, memory_fit, disk_fit, guest_fit), 0)


def _weighted_headroom_score(
    node: NodeCapacity,
    *,
    cores: float,
    memory_bytes: int,
    disk_bytes: int,
) -> float:
    cpu_total = max(node.total_cpu_cores, 1.0)
    memory_total = max(float(node.total_memory_bytes), 1.0)
    disk_total = max(float(node.total_disk_bytes), 1.0)
    guest_total = max(float(node.guest_soft_limit), 1.0)

    cpu_headroom = max(node.allocatable_cpu_cores - cores, 0.0) / cpu_total
    memory_headroom = max(node.allocatable_memory_bytes - memory_bytes, 0) / memory_total
    disk_headroom = max(node.allocatable_disk_bytes - disk_bytes, 0) / disk_total
    guest_headroom = max(node.guest_soft_limit - node.running_resources - 1, 0) / guest_total

    return (
        (settings.placement_weight_cpu * cpu_headroom)
        + (settings.placement_weight_memory * memory_headroom)
        + (settings.placement_weight_disk * disk_headroom)
        + (settings.placement_weight_guest * guest_headroom)
    )


def _can_fit(
    node: NodeCapacity,
    *,
    cores: float,
    memory_bytes: int,
    disk_bytes: int,
    gpu_required: int,
) -> bool:
    return (
        node.allocatable_cpu_cores >= cores
        and node.allocatable_memory_bytes >= memory_bytes
        and node.allocatable_disk_bytes >= disk_bytes
        and node.gpu_count >= gpu_required
        and node.running_resources < node.guest_soft_limit
    )


def _effective_cpu_cores(request: PlacementRequest) -> float:
    requested = float(request.cores)
    if request.estimated_users_per_instance <= 0:
        return requested
    user_driven_cpu = request.estimated_users_per_instance / settings.safe_users_per_cpu
    return round(max(requested, user_driven_cpu), 2)


def _effective_memory_bytes(request: PlacementRequest) -> int:
    requested = request.memory_mb * MIB
    if request.estimated_users_per_instance <= 0:
        return requested
    user_driven_memory_mb = ceil(
        (request.estimated_users_per_instance / settings.safe_users_per_gib) * 1024
    )
    return max(requested, user_driven_memory_mb * MIB)


def _guest_soft_limit(maxcpu: int) -> int:
    return max(int(maxcpu * settings.guest_per_core_limit), 1)


def _guest_pressure_ratio(running_resources: int, maxcpu: int) -> float:
    guest_limit = _guest_soft_limit(maxcpu)
    if guest_limit <= 0:
        return 0.0
    return max(float(running_resources) / float(guest_limit), 0.0)


def _raw_available_cpu(node: NodeSnapshot) -> float:
    used_cpu = max(float(node.maxcpu) * node.cpu_ratio, 0.0)
    return max(float(node.maxcpu) - used_cpu, 0.0)


def _raw_available_bytes(used: int, total: int) -> int:
    return max(total - used, 0)


def _safe_available_float(raw_available: float, total: int) -> float:
    reserve = float(total) * settings.placement_headroom_ratio
    return max(raw_available - reserve, 0.0)


def _safe_available_int(raw_available: int, total: int) -> int:
    reserve = int(total * settings.placement_headroom_ratio)
    return max(raw_available - reserve, 0)


def _ratio(used: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return max(float(used) / float(total), 0.0)


def _optional_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
