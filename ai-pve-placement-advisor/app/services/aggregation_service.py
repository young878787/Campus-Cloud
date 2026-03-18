from __future__ import annotations

from collections import Counter
from math import ceil, floor
from typing import Iterable

from app.core.config import settings
from app.schemas import (
    AggregationSummary,
    EventItem,
    FeatureItem,
    NodeCapacity,
    NodeSnapshot,
    PlacementDecision,
    PlacementRecommendation,
    PlacementRequest,
    RecommendationItem,
    ResourceSnapshot,
)


GIB = 1024**3
MIB = 1024**2


def build_aggregation_summary(
    *,
    nodes: list[NodeSnapshot],
    resources: list[ResourceSnapshot],
) -> AggregationSummary:
    resource_counter = Counter(resource.node for resource in resources)
    guest_ratios = [
        _guest_pressure_ratio(resource_counter.get(node.node, 0), node.maxcpu)
        for node in nodes
    ]

    avg_node_cpu = _average(item.cpu_ratio for item in nodes)
    avg_node_memory = _average(_ratio(item.mem_bytes, item.maxmem_bytes) for item in nodes)
    avg_node_disk = _average(_ratio(item.disk_bytes, item.maxdisk_bytes) for item in nodes)
    avg_guest_ratio = _average(guest_ratios)
    guest_overloaded_count = sum(
        1 for ratio in guest_ratios if ratio >= settings.guest_pressure_threshold
    )

    return AggregationSummary(
        stair_coefficient=settings.aggregation_stair_coefficient,
        node_count=len(nodes),
        resource_count=len(resources),
        total_cpu_capacity=sum(item.maxcpu for item in nodes),
        total_memory_bytes=sum(item.maxmem_bytes for item in nodes),
        total_disk_bytes=sum(item.maxdisk_bytes for item in nodes),
        available_cpu_cores=sum(_raw_available_cpu(item) for item in nodes),
        available_memory_bytes=sum(
            _raw_available_bytes(item.mem_bytes, item.maxmem_bytes) for item in nodes
        ),
        available_disk_bytes=sum(
            _raw_available_bytes(item.disk_bytes, item.maxdisk_bytes) for item in nodes
        ),
        avg_node_cpu_ratio=avg_node_cpu,
        avg_node_memory_ratio=avg_node_memory,
        avg_node_disk_ratio=avg_node_disk,
        avg_guest_pressure_ratio=avg_guest_ratio,
        guest_overloaded_node_count=guest_overloaded_count,
        cluster_health=_cluster_health(
            avg_node_cpu,
            avg_node_memory,
            avg_node_disk,
            avg_guest_ratio,
        ),
    )


def build_node_capacities(
    *,
    nodes: list[NodeSnapshot],
    resources: list[ResourceSnapshot],
) -> list[NodeCapacity]:
    resource_counter = Counter(resource.node for resource in resources)
    node_capacities: list[NodeCapacity] = []

    for node in nodes:
        running_resources = resource_counter.get(node.node, 0)
        guest_soft_limit = _guest_soft_limit(node.maxcpu)
        guest_pressure_ratio = _guest_pressure_ratio(running_resources, node.maxcpu)
        guest_overloaded = guest_pressure_ratio >= settings.guest_pressure_threshold

        raw_available_cpu = _raw_available_cpu(node)
        raw_available_memory = _raw_available_bytes(node.mem_bytes, node.maxmem_bytes)
        raw_available_disk = _raw_available_bytes(node.disk_bytes, node.maxdisk_bytes)
        allocatable_cpu = _safe_available_float(raw_available_cpu, node.maxcpu)
        allocatable_memory = _safe_available_int(raw_available_memory, node.maxmem_bytes)
        allocatable_disk = _safe_available_int(raw_available_disk, node.maxdisk_bytes)

        candidate = (
            node.status == "online"
            and allocatable_cpu > 0
            and allocatable_memory > 0
            and allocatable_disk > 0
            and not guest_overloaded
        )

        node_capacities.append(
            NodeCapacity(
                node=node.node,
                status=node.status,
                running_resources=running_resources,
                guest_soft_limit=guest_soft_limit,
                guest_pressure_ratio=guest_pressure_ratio,
                guest_overloaded=guest_overloaded,
                candidate=candidate,
                cpu_ratio=node.cpu_ratio,
                memory_ratio=_ratio(node.mem_bytes, node.maxmem_bytes),
                disk_ratio=_ratio(node.disk_bytes, node.maxdisk_bytes),
                total_cpu_cores=float(node.maxcpu),
                used_cpu_cores=max(float(node.maxcpu) * node.cpu_ratio, 0.0),
                raw_available_cpu_cores=raw_available_cpu,
                allocatable_cpu_cores=allocatable_cpu,
                total_memory_bytes=node.maxmem_bytes,
                used_memory_bytes=node.mem_bytes,
                raw_available_memory_bytes=raw_available_memory,
                allocatable_memory_bytes=allocatable_memory,
                total_disk_bytes=node.maxdisk_bytes,
                used_disk_bytes=node.disk_bytes,
                raw_available_disk_bytes=raw_available_disk,
                allocatable_disk_bytes=allocatable_disk,
            )
        )

    return sorted(node_capacities, key=lambda item: item.node)


def build_features(
    summary: AggregationSummary,
    node_capacities: list[NodeCapacity],
) -> list[FeatureItem]:
    busiest = max(
        node_capacities,
        key=lambda item: max(
            item.cpu_ratio,
            item.memory_ratio,
            item.disk_ratio,
            item.guest_pressure_ratio,
        ),
        default=None,
    )
    safest = max(
        node_capacities,
        key=lambda item: (
            item.allocatable_cpu_cores,
            item.allocatable_memory_bytes,
            item.allocatable_disk_bytes,
            -item.guest_pressure_ratio,
        ),
        default=None,
    )

    return [
        FeatureItem(
            key="cluster_health",
            value=summary.cluster_health,
            description="整體節點壓力，綜合 CPU、記憶體、磁碟與 Guest 密度判斷。",
        ),
        FeatureItem(
            key="available_cpu_cores",
            value=round(summary.available_cpu_cores, 2),
            description="所有節點目前合計可用 CPU core。",
        ),
        FeatureItem(
            key="available_memory_gb",
            value=round(summary.available_memory_bytes / GIB, 2),
            description="所有節點目前合計可用記憶體。",
        ),
        FeatureItem(
            key="available_disk_gb",
            value=round(summary.available_disk_bytes / GIB, 2),
            description="所有節點目前合計可用磁碟空間。",
        ),
        FeatureItem(
            key="avg_guest_pressure_ratio",
            value=round(summary.avg_guest_pressure_ratio, 2),
            description="目前平均 Guest 壓力比，對照各節點建議承載上限。",
        ),
        FeatureItem(
            key="busiest_node",
            value=busiest.node if busiest else None,
            description="目前整體壓力最高的節點。",
        ),
        FeatureItem(
            key="best_fit_node",
            value=safest.node if safest else None,
            description="目前保留安全餘裕最多的節點。",
        ),
    ]


def build_placement_recommendation(
    *,
    request: PlacementRequest,
    node_capacities: list[NodeCapacity],
) -> PlacementRecommendation:
    working_nodes = [item.model_copy(deep=True) for item in node_capacities]
    configured_memory = request.memory_mb * MIB
    req_disk = request.disk_gb * GIB
    effective_cpu = _effective_cpu_cores(request)
    effective_memory = _effective_memory_bytes(request)
    user_pressure_level = _user_pressure_level(request, effective_cpu, effective_memory)
    placements: dict[str, int] = {item.node: 0 for item in working_nodes}
    remaining = request.instance_count

    while remaining > 0:
        candidates = [
            item
            for item in working_nodes
            if item.candidate and _can_fit(item, effective_cpu, effective_memory, req_disk)
        ]
        if not candidates:
            break

        chosen = _choose_node(
            nodes=candidates,
            placements=placements,
            cores=effective_cpu,
            req_memory=effective_memory,
            req_disk=req_disk,
        )
        placements[chosen.node] += 1
        chosen.allocatable_cpu_cores = max(chosen.allocatable_cpu_cores - effective_cpu, 0.0)
        chosen.allocatable_memory_bytes = max(
            chosen.allocatable_memory_bytes - effective_memory,
            0,
        )
        chosen.allocatable_disk_bytes = max(chosen.allocatable_disk_bytes - req_disk, 0)
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
    decisions = [
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

    placement_nodes = [f"{item.node} x{item.instance_count}" for item in decisions]
    candidate_cpu = sum(item.allocatable_cpu_cores for item in node_capacities if item.candidate)
    candidate_memory = sum(
        item.allocatable_memory_bytes for item in node_capacities if item.candidate
    )
    candidate_disk = sum(item.allocatable_disk_bytes for item in node_capacities if item.candidate)
    overloaded_nodes = [item.node for item in node_capacities if item.guest_overloaded]

    rationale = [
        (
            f"目前可安全配置總量約為 CPU {candidate_cpu:.1f}、"
            f"記憶體 {candidate_memory / GIB:.1f} GiB、磁碟 {candidate_disk / GIB:.1f} GiB。"
        ),
        "系統會同時評估 CPU、記憶體、磁碟、Guest 數量，以及每台預估承載的使用者壓力。",
    ]

    if request.estimated_users_per_instance > 0:
        rationale.append(
            (
                f"每台預估 {request.estimated_users_per_instance} 人同時使用，"
                f"安全規劃等效為每台 {effective_cpu:.1f} CPU、"
                f"{effective_memory / GIB:.1f} GiB 記憶體。"
            )
        )

    if overloaded_nodes:
        rationale.append(f"Guest 數量偏高的節點已降低優先順序：{', '.join(overloaded_nodes)}。")

    if assigned == 0:
        summary = (
            f"目前安全餘裕不足，無法放入任何 {request.machine_name}。"
            f"需求 {request.instance_count} 台，實際可配置 0 台。"
        )
    elif remaining == 0:
        summary = (
            f"建議將 {request.instance_count} 台 {request.machine_name} 分配到："
            f"{', '.join(placement_nodes)}。"
        )
    else:
        summary = (
            f"目前僅能安全配置 {assigned} / {request.instance_count} 台 {request.machine_name}："
            f"{', '.join(placement_nodes)}。"
        )

    return PlacementRecommendation(
        request=request,
        feasible=remaining == 0,
        assigned_instances=assigned,
        unassigned_instances=remaining,
        effective_cpu_cores_per_instance=round(effective_cpu, 2),
        effective_memory_bytes_per_instance=effective_memory,
        user_pressure_level=user_pressure_level,
        summary=summary,
        rationale=rationale,
        placements=decisions,
        candidate_nodes=working_nodes,
    )


def build_events(
    *,
    summary: AggregationSummary,
    placement: PlacementRecommendation | None = None,
) -> list[EventItem]:
    events: list[EventItem] = []

    if summary.avg_node_cpu_ratio >= settings.cpu_high_threshold:
        level = _stair_level(summary.avg_node_cpu_ratio, settings.cpu_high_threshold)
        events.append(
            EventItem(
                code="high_cpu",
                severity=_severity_from_level(level),
                score=level,
                summary="叢集 CPU 壓力已偏高。",
                evidence={"avg_node_cpu_ratio": round(summary.avg_node_cpu_ratio, 3)},
            )
        )

    if summary.avg_node_memory_ratio >= settings.memory_high_threshold:
        level = _stair_level(summary.avg_node_memory_ratio, settings.memory_high_threshold)
        events.append(
            EventItem(
                code="high_memory",
                severity=_severity_from_level(level),
                score=level,
                summary="叢集記憶體壓力已偏高。",
                evidence={"avg_node_memory_ratio": round(summary.avg_node_memory_ratio, 3)},
            )
        )

    if summary.avg_node_disk_ratio >= settings.disk_high_threshold:
        level = _stair_level(summary.avg_node_disk_ratio, settings.disk_high_threshold)
        events.append(
            EventItem(
                code="high_disk",
                severity=_severity_from_level(level),
                score=level,
                summary="叢集磁碟使用率接近安全配置上限。",
                evidence={"avg_node_disk_ratio": round(summary.avg_node_disk_ratio, 3)},
            )
        )

    if summary.guest_overloaded_node_count > 0:
        level = _stair_level(summary.avg_guest_pressure_ratio, settings.guest_pressure_threshold)
        events.append(
            EventItem(
                code="guest_overload",
                severity=_severity_from_level(level),
                score=max(level, 2),
                summary="部分節點 Guest 數量已偏高，可能增加過載風險。",
                evidence={
                    "avg_guest_pressure_ratio": round(summary.avg_guest_pressure_ratio, 3),
                    "guest_overloaded_node_count": summary.guest_overloaded_node_count,
                },
            )
        )

    if placement is not None:
        if placement.request.estimated_users_per_instance > 0:
            score_map = {"low": 2, "medium": 3, "high": 4}
            severity_map = {"low": "medium", "medium": "high", "high": "high"}
            if placement.user_pressure_level != "none":
                events.append(
                    EventItem(
                        code="user_pressure",
                        severity=severity_map.get(placement.user_pressure_level, "medium"),
                        score=score_map.get(placement.user_pressure_level, 2),
                        summary="本次配置已納入預估使用者壓力與 CPU / 記憶體關係。",
                        evidence={
                            "estimated_users_per_instance": placement.request.estimated_users_per_instance,
                            "effective_cpu_cores_per_instance": placement.effective_cpu_cores_per_instance,
                            "effective_memory_gib_per_instance": round(
                                placement.effective_memory_bytes_per_instance / GIB,
                                2,
                            ),
                        },
                    )
                )

        if placement.assigned_instances == 0:
            events.append(
                EventItem(
                    code="placement_blocked",
                    severity="critical",
                    score=5,
                    summary="沒有節點能安全承載本次需求。",
                    evidence={"requested": placement.request.instance_count, "assigned": 0},
                )
            )
        elif placement.unassigned_instances > 0:
            events.append(
                EventItem(
                    code="partial_fit",
                    severity="high",
                    score=4,
                    summary="只有部分相同規格實例能安全放入。",
                    evidence={
                        "requested": placement.request.instance_count,
                        "assigned": placement.assigned_instances,
                        "unassigned": placement.unassigned_instances,
                    },
                )
            )
        else:
            events.append(
                EventItem(
                    code="placement_ready",
                    severity="low",
                    score=1,
                    summary="目前叢集安全餘裕足以承載本次需求。",
                    evidence={"requested": placement.request.instance_count},
                )
            )

    if not events:
        events.append(
            EventItem(
                code="healthy_window",
                severity="info",
                score=1,
                summary="目前未發現會阻擋配置的風險。",
                evidence={},
            )
        )

    return events


def build_recommendations(
    *,
    events: list[EventItem],
    summary: AggregationSummary,
    node_capacities: list[NodeCapacity],
    placement: PlacementRecommendation | None = None,
) -> list[RecommendationItem]:
    recommendations: list[RecommendationItem] = []

    if placement is not None and placement.request.estimated_users_per_instance > 0:
        recommendations.append(
            RecommendationItem(
                target="user-pressure",
                action="已將使用者壓力納入安全規劃",
                reason=(
                    f"每台預估 {placement.request.estimated_users_per_instance} 人同時使用，"
                    f"因此系統以每台 {placement.effective_cpu_cores_per_instance:.1f} CPU、"
                    f"{placement.effective_memory_bytes_per_instance / GIB:.1f} GiB 記憶體做安全判斷，"
                    "而不是只看表單填寫的原始規格。"
                ),
            )
        )

    if placement is not None and placement.placements:
        placement_text = "、".join(
            f"{item.node} 放 {item.instance_count} 台" for item in placement.placements
        )
        recommendations.append(
            RecommendationItem(
                target="placement",
                action=f"建議分配：{placement_text}",
                reason=_placement_reason(placement, node_capacities),
            )
        )

    if placement is not None:
        placed_nodes = {item.node for item in placement.placements}
        for node in node_capacities:
            if node.node in placed_nodes:
                continue
            recommendations.append(
                RecommendationItem(
                    target="placement-reason",
                    action=f"{node.node} 本次未優先配置",
                    reason=_node_skip_reason(node, placement),
                )
            )

    if placement is not None and placement.unassigned_instances > 0:
        recommendations.append(
            RecommendationItem(
                target="capacity",
                action="目前安全容量不足以完全滿足需求",
                reason=(
                    f"仍有 {placement.unassigned_instances} 台無法安全放入，"
                    "代表目前至少一項資源、Guest 承載量，或使用者壓力推導出的 CPU / 記憶體需求已達限制。"
                ),
            )
        )

    for event in events:
        if event.code == "high_cpu":
            recommendations.append(
                RecommendationItem(
                    target="cluster",
                    action="整體 CPU 壓力偏高",
                    reason="即使目前尚可配置，仍要避免再集中放在 CPU 已高的節點。"
                    "若持續增加工作負載，應考慮分散或擴充節點。",
                )
            )
        elif event.code == "high_memory":
            recommendations.append(
                RecommendationItem(
                    target="cluster",
                    action="整體記憶體壓力偏高",
                    reason="記憶體是目前主要風險之一，新的 Guest 應優先放到記憶體餘裕較大的節點。"
                    "若需求持續增加，應考慮調整現有 VM/LXC 或擴充容量。",
                )
            )
        elif event.code == "high_disk":
            recommendations.append(
                RecommendationItem(
                    target="storage",
                    action="整體磁碟壓力偏高",
                    reason="磁碟安全餘裕已下降，新的配置需避免落在剩餘空間較少的節點。",
                )
            )
        elif event.code == "guest_overload":
            recommendations.append(
                RecommendationItem(
                    target="guest-density",
                    action="部分節點 Guest 數量過高",
                    reason="除了 CPU、記憶體、磁碟外，系統也會評估每台節點承載的 Guest 數量。"
                    "當 Guest 太多時，即使單看資源似乎夠，也可能增加排程與過載風險。",
                )
            )
        elif event.code == "user_pressure":
            recommendations.append(
                RecommendationItem(
                    target="user-pressure",
                    action="使用者壓力已影響本次配置判斷",
                    reason="當預估同時使用人數提高時，系統會自動提高 CPU 與記憶體的安全規劃需求，"
                    "避免只看靜態規格而低估實際負載。",
                )
            )

    if not recommendations:
        best_node = max(
            node_capacities,
            key=lambda item: (
                item.allocatable_cpu_cores,
                item.allocatable_memory_bytes,
                item.allocatable_disk_bytes,
                -item.guest_pressure_ratio,
            ),
            default=None,
        )
        recommendations.append(
            RecommendationItem(
                target="cluster",
                action=f"建議優先使用 {best_node.node}" if best_node else "目前沒有可建議節點",
                reason=(
                    f"{best_node.node} 目前保留較多安全 CPU、記憶體、磁碟與較低 Guest 壓力。"
                    if best_node
                    else "目前沒有 online 且可安全配置的節點。"
                ),
            )
        )

    return recommendations


def build_summary(
    *,
    summary: AggregationSummary,
    placement: PlacementRecommendation | None = None,
    events: list[EventItem],
) -> str:
    if placement is not None:
        top_event = max(events, key=lambda item: item.score)
        if top_event.code in {"placement_blocked", "partial_fit"}:
            return f"{placement.summary} 目前叢集健康狀態為 {summary.cluster_health}。"
        return placement.summary

    return (
        f"目前可見叢集共有 {summary.node_count} 台節點、"
        f"{summary.resource_count} 台 Guest，"
        f"可用 CPU 約 {summary.available_cpu_cores:.1f} core、"
        f"可用記憶體約 {summary.available_memory_bytes / GIB:.1f} GiB、"
        f"可用磁碟約 {summary.available_disk_bytes / GIB:.1f} GiB。"
        f"平均 Guest 壓力比為 {summary.avg_guest_pressure_ratio:.2f}，"
        f"目前叢集健康狀態為 {summary.cluster_health}。"
    )


def _placement_reason(
    placement: PlacementRecommendation,
    node_capacities: list[NodeCapacity],
) -> str:
    capacity_map = {item.node: item for item in node_capacities}
    reasons: list[str] = []

    if placement.request.estimated_users_per_instance > 0:
        reasons.append(
            (
                f"每台預估 {placement.request.estimated_users_per_instance} 人，"
                f"因此本次用每台 {placement.effective_cpu_cores_per_instance:.1f} CPU、"
                f"{placement.effective_memory_bytes_per_instance / GIB:.1f} GiB 記憶體做安全規劃"
            )
        )

    for item in placement.placements:
        baseline = capacity_map.get(item.node)
        guest_reason = ""
        if baseline is not None:
            projected_guests = baseline.running_resources + item.instance_count
            guest_reason = (
                f"；Guest 數量將從 {baseline.running_resources} 台增加到 {projected_guests} 台，"
                f"仍低於建議上限 {baseline.guest_soft_limit} 台"
            )

        reasons.append(
            f"{item.node} 分配後仍保留 {item.remaining_cpu_cores:.1f} CPU、"
            f"{item.remaining_memory_bytes / GIB:.1f} GiB 記憶體、"
            f"{item.remaining_disk_bytes / GIB:.1f} GiB 磁碟"
            f"{guest_reason}"
        )

    if placement.unassigned_instances > 0:
        reasons.append(f"仍有 {placement.unassigned_instances} 台無法安全放入。")

    return "；".join(reasons)


def _node_skip_reason(
    node: NodeCapacity,
    placement: PlacementRecommendation,
) -> str:
    request = placement.request
    req_disk = request.disk_gb * GIB
    effective_cpu = placement.effective_cpu_cores_per_instance
    effective_memory = placement.effective_memory_bytes_per_instance

    if node.status != "online":
        return "該節點目前不是 online 狀態，因此不納入本次配置。"

    shortages: list[str] = []
    if node.allocatable_cpu_cores < effective_cpu:
        shortages.append(
            f"安全可配 CPU 只有 {node.allocatable_cpu_cores:.1f}，低於需求的 {effective_cpu:.1f}"
        )
    if node.allocatable_memory_bytes < effective_memory:
        shortages.append(
            f"安全可配記憶體只有 {node.allocatable_memory_bytes / GIB:.1f} GiB，"
            f"低於需求的 {effective_memory / GIB:.1f} GiB"
        )
    if node.allocatable_disk_bytes < req_disk:
        shortages.append(
            f"安全可配磁碟只有 {node.allocatable_disk_bytes / GIB:.1f} GiB，"
            f"低於需求的 {req_disk / GIB:.1f} GiB"
        )
    if node.guest_overloaded:
        shortages.append(
            f"目前已承載 {node.running_resources} 台 Guest，接近或超過建議上限 {node.guest_soft_limit} 台"
        )

    if shortages:
        return "因為" + "，".join(shortages) + "。"

    if request.estimated_users_per_instance > 0:
        return (
            f"這台雖然仍有部分餘裕，但面對每台預估 {request.estimated_users_per_instance} 人的負載時，"
            f"相較其他節點可保留的 CPU / 記憶體安全空間較少，因此本次優先放在其他台。"
        )

    return (
        f"雖然這台仍有部分餘裕，但目前已承載 {node.running_resources} 台 Guest，"
        f"Guest 壓力比為 {node.guest_pressure_ratio:.2f}。"
        "相較之下，其他節點本次能保留更多安全餘裕，因此優先放在其他台。"
    )


def _choose_node(
    *,
    nodes: list[NodeCapacity],
    placements: dict[str, int],
    cores: float,
    req_memory: int,
    req_disk: int,
) -> NodeCapacity:
    return max(
        nodes,
        key=lambda item: (
            -placements[item.node],
            _fit_count(item, cores=cores, memory_bytes=req_memory, disk_bytes=req_disk),
            _slack_score(item, cores=cores, memory_bytes=req_memory, disk_bytes=req_disk),
            -item.guest_pressure_ratio,
        ),
    )


def _fit_count(node: NodeCapacity, cores: float, memory_bytes: int, disk_bytes: int) -> int:
    cpu_fit = floor(node.allocatable_cpu_cores / float(cores)) if cores > 0 else 0
    memory_fit = floor(node.allocatable_memory_bytes / memory_bytes) if memory_bytes > 0 else 0
    disk_fit = floor(node.allocatable_disk_bytes / disk_bytes) if disk_bytes > 0 else 0
    guest_fit = max(node.guest_soft_limit - node.running_resources, 0)
    return max(min(cpu_fit, memory_fit, disk_fit, guest_fit), 0)


def _slack_score(node: NodeCapacity, cores: float, memory_bytes: int, disk_bytes: int) -> float:
    return (
        max(node.allocatable_cpu_cores - cores, 0.0)
        + max((node.allocatable_memory_bytes - memory_bytes) / GIB, 0.0)
        + max((node.allocatable_disk_bytes - disk_bytes) / GIB, 0.0)
        + max(node.guest_soft_limit - node.running_resources - 1, 0)
    )


def _can_fit(node: NodeCapacity, cores: float, memory_bytes: int, disk_bytes: int) -> bool:
    return (
        node.allocatable_cpu_cores >= cores
        and node.allocatable_memory_bytes >= memory_bytes
        and node.allocatable_disk_bytes >= disk_bytes
        and node.running_resources < node.guest_soft_limit
    )


def _cluster_health(
    cpu_ratio: float,
    memory_ratio: float,
    disk_ratio: float,
    guest_ratio: float,
) -> str:
    highest = max(cpu_ratio, memory_ratio, disk_ratio, guest_ratio)
    if highest >= 0.9:
        return "critical"
    if highest >= 0.8:
        return "stressed"
    if highest >= 0.6:
        return "watch"
    return "healthy"


def _guest_soft_limit(maxcpu: int) -> int:
    return max(int(maxcpu * settings.guest_per_core_limit), 1)


def _guest_pressure_ratio(running_resources: int, maxcpu: int) -> float:
    guest_limit = _guest_soft_limit(maxcpu)
    if guest_limit <= 0:
        return 0.0
    return max(float(running_resources) / float(guest_limit), 0.0)


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


def _user_pressure_level(
    request: PlacementRequest,
    effective_cpu: float,
    effective_memory: int,
) -> str:
    if request.estimated_users_per_instance <= 0:
        return "none"

    cpu_multiplier = effective_cpu / max(float(request.cores), 1.0)
    memory_multiplier = effective_memory / max(request.memory_mb * MIB, MIB)
    highest = max(cpu_multiplier, memory_multiplier)

    if highest >= 2.0:
        return "high"
    if highest >= 1.4:
        return "medium"
    return "low"


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


def _average(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _stair_level(value: float, threshold: float) -> int:
    if threshold <= 0 or value < threshold:
        return 1 if value > 0 else 0

    level = 1
    multiplier = settings.aggregation_stair_coefficient
    current = threshold * multiplier

    while value >= current and level < 5:
        level += 1
        current *= multiplier

    return level


def _severity_from_level(level: int) -> str:
    if level >= 5:
        return "critical"
    if level >= 4:
        return "high"
    if level >= 2:
        return "medium"
    return "low"
