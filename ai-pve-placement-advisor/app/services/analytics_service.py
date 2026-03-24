from __future__ import annotations

import asyncio
from dataclasses import dataclass
import threading
import time

from app.core.config import settings
from app.schemas import (
    AnalysisResponse,
    BackendTrafficSnapshot,
    PlacementRequest,
    RuntimeMetrics,
    SourceHealth,
    SourcePreviewResponse,
)
from app.services import aggregation_service
from app.services import backend_source_service
from app.services import metrics_service
from app.services import proxmox_source_service
from app.services import snapshot_source_service


@dataclass
class _PreviewCacheEntry:
    cached_at: float
    preview: SourcePreviewResponse


_preview_cache: _PreviewCacheEntry | None = None
_preview_cache_lock = threading.Lock()


async def build_source_preview() -> SourcePreviewResponse:
    if settings.source_cache_ttl_seconds > 0:
        cached = _get_cached_preview()
        if cached is not None:
            return cached

    nodes = []
    resources = []
    token_usage = snapshot_source_service.load_token_usage_snapshots()
    gpu_metrics = snapshot_source_service.load_gpu_metric_snapshots()
    backend_traffic: BackendTrafficSnapshot | None = None
    source_health: list[SourceHealth] = []

    if not nodes and settings.use_direct_proxmox:
        try:
            nodes, resources = await asyncio.gather(
                asyncio.to_thread(proxmox_source_service.fetch_nodes),
                asyncio.to_thread(proxmox_source_service.fetch_resources),
            )
            source_health.append(
                SourceHealth(
                    name="proxmox",
                    available=True,
                    mode="direct",
                    detail="Fetched nodes and VM/LXC resources from Proxmox.",
                    record_count=len(nodes) + len(resources),
                )
            )
        except Exception as exc:
            metrics_service.increment_proxmox_failure()
            source_health.append(
                SourceHealth(
                    name="proxmox",
                    available=False,
                    mode="direct",
                    detail=str(exc),
                    record_count=0,
                )
            )

    if not nodes:
        nodes = snapshot_source_service.load_node_snapshots()
        source_health.append(
            SourceHealth(
                name="node_snapshot",
                available=bool(nodes),
                mode="snapshot",
                detail="Loaded node snapshot data from env JSON.",
                record_count=len(nodes),
            )
        )

    if token_usage:
        source_health.append(
            SourceHealth(
                name="token_snapshot",
                available=True,
                mode="snapshot",
                detail="Loaded token-usage snapshots from env JSON.",
                record_count=len(token_usage),
            )
        )
    else:
        source_health.append(
            SourceHealth(
                name="token_snapshot",
                available=False,
                mode="snapshot",
                detail="No token snapshot configured.",
                record_count=0,
            )
        )

    if gpu_metrics:
        source_health.append(
            SourceHealth(
                name="gpu_snapshot",
                available=True,
                mode="snapshot",
                detail="Loaded GPU metric snapshots from env JSON.",
                record_count=len(gpu_metrics),
            )
        )
    else:
        source_health.append(
            SourceHealth(
                name="gpu_snapshot",
                available=False,
                mode="snapshot",
                detail="No GPU metric snapshot configured.",
                record_count=0,
            )
        )

    if settings.backend_api_base_url and settings.backend_api_token:
        try:
            backend_traffic = await asyncio.to_thread(
                backend_source_service.fetch_backend_traffic_snapshot
            )
            source_health.append(
                SourceHealth(
                    name="backend_traffic",
                    available=backend_traffic is not None,
                    mode="direct",
                    detail=(
                        "Fetched VM request traffic from backend API."
                        if backend_traffic is not None
                        else "Backend API returned no usable payload."
                    ),
                    record_count=backend_traffic.sample_size if backend_traffic else 0,
                )
            )
        except Exception as exc:
            metrics_service.increment_backend_traffic_failure()
            source_health.append(
                SourceHealth(
                    name="backend_traffic",
                    available=False,
                    mode="direct",
                    detail=str(exc),
                    record_count=0,
                )
            )
    else:
        source_health.append(
            SourceHealth(
                name="backend_traffic",
                available=False,
                mode="disabled",
                detail="Set BACKEND_API_BASE_URL and BACKEND_API_TOKEN to enable backend traffic ingestion.",
                record_count=0,
            )
        )

    preview = SourcePreviewResponse(
        source_health=source_health,
        nodes=nodes,
        resources=resources,
        token_usage=token_usage,
        gpu_metrics=gpu_metrics,
        backend_traffic=backend_traffic,
    )
    _set_cached_preview(preview)
    return preview


async def build_analysis(
    placement_request: PlacementRequest | None = None,
) -> AnalysisResponse:
    started = time.perf_counter()
    preview = await build_source_preview()
    aggregation = aggregation_service.build_aggregation_summary(
        nodes=preview.nodes,
        resources=preview.resources,
    )
    node_capacities = aggregation_service.build_node_capacities(
        nodes=preview.nodes,
        resources=preview.resources,
    )
    features = aggregation_service.build_features(aggregation, node_capacities)
    if preview.backend_traffic is not None:
        features.extend(
            [
                aggregation_service.backend_traffic_to_feature(
                    key="backend_submitted_in_window",
                    value=preview.backend_traffic.submitted_in_window,
                    description=(
                        f"最近 {preview.backend_traffic.window_minutes} 分鐘 backend 新增申請數。"
                    ),
                ),
                aggregation_service.backend_traffic_to_feature(
                    key="backend_pending_total",
                    value=preview.backend_traffic.pending_total,
                    description="目前 backend 待審核申請數（可視為短期需求壓力）。",
                ),
            ]
        )
    placement = (
        aggregation_service.build_placement_recommendation(
            request=placement_request,
            node_capacities=node_capacities,
        )
        if placement_request
        else None
    )
    events = aggregation_service.build_events(
        summary=aggregation,
        placement=placement,
        backend_traffic=preview.backend_traffic,
    )
    recommendations = aggregation_service.build_recommendations(
        events=events,
        summary=aggregation,
        node_capacities=node_capacities,
        placement=placement,
        backend_traffic=preview.backend_traffic,
    )
    summary = aggregation_service.build_summary(
        summary=aggregation,
        placement=placement,
        events=events,
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    metrics_service.observe_analysis(
        duration_ms=elapsed_ms,
        with_placement=placement_request is not None,
    )
    runtime_metrics = RuntimeMetrics(**metrics_service.snapshot())

    return AnalysisResponse(
        source_health=preview.source_health,
        aggregation=aggregation,
        features=features,
        events=events,
        recommendations=recommendations,
        summary=summary,
        runtime_metrics=runtime_metrics,
        nodes=preview.nodes,
        resources=preview.resources,
        node_capacities=node_capacities,
        placement=placement,
        backend_traffic=preview.backend_traffic,
    )


def get_runtime_metrics() -> RuntimeMetrics:
    return RuntimeMetrics(**metrics_service.snapshot())


def _get_cached_preview() -> SourcePreviewResponse | None:
    with _preview_cache_lock:
        if _preview_cache is None:
            return None
        age = time.monotonic() - _preview_cache.cached_at
        if age > settings.source_cache_ttl_seconds:
            return None
        return _preview_cache.preview


def _set_cached_preview(preview: SourcePreviewResponse) -> None:
    if settings.source_cache_ttl_seconds <= 0:
        return
    with _preview_cache_lock:
        global _preview_cache
        _preview_cache = _PreviewCacheEntry(
            cached_at=time.monotonic(),
            preview=preview,
        )
