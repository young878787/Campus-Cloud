from __future__ import annotations

from typing import Iterable

from app.core.config import settings
from app.schemas import (
    AggregationSummary,
    AuditLogEntry,
    EventItem,
    FeatureItem,
    GpuMetricSnapshot,
    NodeSnapshot,
    RecommendationItem,
    ResourceSnapshot,
    TokenUsageSnapshot,
)


def build_aggregation_summary(
    *,
    nodes: list[NodeSnapshot],
    resources: list[ResourceSnapshot],
    audit_logs: list[AuditLogEntry],
    token_usage: list[TokenUsageSnapshot],
    gpu_metrics: list[GpuMetricSnapshot],
) -> AggregationSummary:
    avg_node_cpu = _average(item.cpu_ratio for item in nodes)
    avg_node_memory = _average(_ratio(item.mem_bytes, item.maxmem_bytes) for item in nodes)
    avg_resource_cpu = _average(item.cpu_ratio for item in resources)
    avg_resource_memory = _average(
        _ratio(item.mem_bytes, item.maxmem_bytes) for item in resources
    )
    total_tokens = sum(item.total_tokens for item in token_usage)
    token_requests = sum(item.requests for item in token_usage)
    token_growth_ratio = _average_optional(item.growth_ratio for item in token_usage)
    gpu_count = sum(item.gpu_count for item in nodes) or sum(item.gpu_count for item in gpu_metrics)
    avg_gpu_util = _average_optional(item.avg_gpu_utilization for item in gpu_metrics)

    return AggregationSummary(
        recent_window_minutes=settings.recent_window_minutes,
        baseline_days=settings.baseline_days,
        aggregation_window_minutes=settings.aggregation_window_minutes,
        stair_coefficient=settings.aggregation_stair_coefficient,
        node_count=len(nodes),
        resource_count=len(resources),
        audit_log_count=len(audit_logs),
        total_cpu_capacity=sum(item.maxcpu for item in nodes),
        avg_node_cpu_ratio=avg_node_cpu,
        avg_node_memory_ratio=avg_node_memory,
        avg_resource_cpu_ratio=avg_resource_cpu,
        avg_resource_memory_ratio=avg_resource_memory,
        gpu_count=gpu_count,
        avg_gpu_utilization=avg_gpu_util,
        total_tokens=total_tokens,
        token_requests=token_requests,
        token_growth_ratio=token_growth_ratio,
    )


def build_features(summary: AggregationSummary) -> list[FeatureItem]:
    return [
        FeatureItem(
            key="node_cpu_stair_level",
            value=_stair_level(summary.avg_node_cpu_ratio, settings.cpu_high_threshold),
            description="Cluster node average CPU pressure level after stair scaling.",
        ),
        FeatureItem(
            key="node_memory_stair_level",
            value=_stair_level(summary.avg_node_memory_ratio, settings.memory_high_threshold),
            description="Cluster node average memory pressure level after stair scaling.",
        ),
        FeatureItem(
            key="resource_memory_peak_risk",
            value=_stair_level(summary.avg_resource_memory_ratio, settings.memory_high_threshold),
            description="Average VM/LXC memory pressure signal.",
        ),
        FeatureItem(
            key="audit_activity_count",
            value=summary.audit_log_count,
            description="Recent audit-log activity in the configured time window.",
        ),
        FeatureItem(
            key="gpu_capacity",
            value=summary.gpu_count,
            description="Total GPU count visible to the analytics service.",
        ),
        FeatureItem(
            key="token_volume",
            value=summary.total_tokens,
            description="Aggregated tokens from configured token snapshots.",
        ),
        FeatureItem(
            key="token_growth_ratio",
            value=summary.token_growth_ratio,
            description="Growth ratio reported by token snapshots.",
        ),
    ]


def build_events(
    *,
    summary: AggregationSummary,
    resources: list[ResourceSnapshot],
    gpu_metrics: list[GpuMetricSnapshot],
    audit_source_available: bool,
) -> list[EventItem]:
    events: list[EventItem] = []

    if summary.avg_node_cpu_ratio >= settings.cpu_high_threshold:
        level = _stair_level(summary.avg_node_cpu_ratio, settings.cpu_high_threshold)
        events.append(
            EventItem(
                code="high_cpu",
                severity=_severity_from_level(level),
                score=level,
                summary="叢集 CPU 負載偏高，已進入資源壓力區間。",
                evidence={
                    "avg_node_cpu_ratio": round(summary.avg_node_cpu_ratio, 3),
                    "threshold": settings.cpu_high_threshold,
                },
            )
        )

    if summary.avg_node_memory_ratio >= settings.memory_high_threshold:
        level = _stair_level(summary.avg_node_memory_ratio, settings.memory_high_threshold)
        events.append(
            EventItem(
                code="high_memory",
                severity=_severity_from_level(level),
                score=level,
                summary="叢集記憶體使用偏高，需留意共用節點的餘裕。",
                evidence={
                    "avg_node_memory_ratio": round(summary.avg_node_memory_ratio, 3),
                    "threshold": settings.memory_high_threshold,
                },
            )
        )

    high_memory_resources = [
        item for item in resources if _ratio(item.mem_bytes, item.maxmem_bytes) >= 0.95
    ]
    if high_memory_resources:
        events.append(
            EventItem(
                code="oom_risk",
                severity="critical",
                score=5,
                summary="至少一個 VM/LXC 已接近記憶體上限，存在 OOM 風險。",
                evidence={
                    "resource_vmids": [item.vmid for item in high_memory_resources[:5]],
                    "count": len(high_memory_resources),
                },
            )
        )

    if (
        summary.token_growth_ratio is not None
        and summary.token_growth_ratio >= settings.token_spike_ratio
    ):
        level = _stair_level(summary.token_growth_ratio, settings.token_spike_ratio)
        events.append(
            EventItem(
                code="token_spike",
                severity=_severity_from_level(level),
                score=level,
                summary="Token 使用量成長過快，可能導致配額或成本異常。",
                evidence={
                    "token_growth_ratio": round(summary.token_growth_ratio, 3),
                    "threshold": settings.token_spike_ratio,
                },
            )
        )

    low_gpu_util_nodes = [
        item
        for item in gpu_metrics
        if item.gpu_count > 0 and (item.avg_gpu_utilization or 0.0) < 20.0
    ]
    if low_gpu_util_nodes:
        events.append(
            EventItem(
                code="gpu_idle_waste",
                severity="medium",
                score=2,
                summary="GPU 節點利用率偏低，存在資源閒置浪費。",
                evidence={
                    "nodes": [item.node for item in low_gpu_util_nodes[:5]],
                    "count": len(low_gpu_util_nodes),
                },
            )
        )

    if not audit_source_available:
        events.append(
            EventItem(
                code="missing_audit_source",
                severity="medium",
                score=2,
                summary="Audit log 資料來源目前不可用，事件解釋會缺少操作脈絡。",
                evidence={"source": "audit_logs"},
            )
        )

    if not events:
        events.append(
            EventItem(
                code="healthy_window",
                severity="info",
                score=1,
                summary="最近視窗內未發現明顯異常，系統維持在可接受範圍。",
                evidence={},
            )
        )

    return events


def build_recommendations(events: list[EventItem]) -> list[RecommendationItem]:
    recommendations: list[RecommendationItem] = []
    for event in events:
        if event.code == "high_cpu":
            recommendations.append(
                RecommendationItem(
                    target="cluster",
                    action="優先把高負載工作移往低載節點，或調整模板 CPU 配置。",
                    reason="CPU 平均負載已超過門檻，若持續堆疊會影響新任務排程。",
                )
            )
        elif event.code == "high_memory":
            recommendations.append(
                RecommendationItem(
                    target="cluster",
                    action="檢查共用節點上大型記憶體工作，必要時拆分或升級記憶體模板。",
                    reason="節點平均記憶體壓力偏高，容易壓縮可用餘裕。",
                )
            )
        elif event.code == "oom_risk":
            recommendations.append(
                RecommendationItem(
                    target="resource",
                    action="優先檢查接近上限的 VM/LXC，調整記憶體或清理長駐程序。",
                    reason="單機資源接近滿載時，會先出現任務失敗與效能抖動。",
                )
            )
        elif event.code == "token_spike":
            recommendations.append(
                RecommendationItem(
                    target="llm",
                    action="加入 token 配額、縮短 prompt、並檢查是否有重複呼叫模式。",
                    reason="Token 成長異常通常代表成本、延遲或濫用風險正在上升。",
                )
            )
        elif event.code == "gpu_idle_waste":
            recommendations.append(
                RecommendationItem(
                    target="gpu",
                    action="將 CPU-only 任務移出 GPU 節點，或集中排程 GPU 工作。",
                    reason="低 GPU 利用率代表配置與實際工作型態不匹配。",
                )
            )
        elif event.code == "missing_audit_source":
            recommendations.append(
                RecommendationItem(
                    target="data-source",
                    action="先恢復 PostgreSQL 或改用 backend audit API，補齊操作紀錄來源。",
                    reason="沒有審計脈絡時，AI 解釋只能依賴基礎監控訊號。",
                )
            )

    if not recommendations:
        recommendations.append(
            RecommendationItem(
                target="system",
                action="維持目前配置，持續收集更多歷史視窗後再進行 AI 比對。",
                reason="目前視窗沒有明顯異常，適合先累積基準資料。",
            )
        )

    return recommendations


def build_summary(events: list[EventItem], summary: AggregationSummary) -> str:
    top_event = max(events, key=lambda item: item.score)
    if top_event.code == "healthy_window":
        return (
            f"最近 {summary.recent_window_minutes} 分鐘內未發現明顯異常，"
            f"目前觀測到 {summary.node_count} 個節點與 {summary.resource_count} 個資源。"
        )
    return (
        f"最近 {summary.recent_window_minutes} 分鐘內偵測到 {len(events)} 個重點事件，"
        f"其中最需要優先處理的是「{top_event.summary}」。"
    )


def _ratio(used: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return max(float(used) / float(total), 0.0)


def _average(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _average_optional(values: Iterable[float | None]) -> float | None:
    items = [value for value in values if value is not None]
    if not items:
        return None
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
