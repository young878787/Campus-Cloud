from __future__ import annotations

from app.core.config import settings
from app.schemas import AnalysisResponse, PlacementRequest, SourceHealth, SourcePreviewResponse
from app.services import aggregation_service
from app.services import proxmox_source_service
from app.services import snapshot_source_service


async def build_source_preview() -> SourcePreviewResponse:
    nodes = []
    resources = []
    token_usage = snapshot_source_service.load_token_usage_snapshots()
    gpu_metrics = snapshot_source_service.load_gpu_metric_snapshots()
    source_health: list[SourceHealth] = []

    if not nodes and settings.use_direct_proxmox:
        try:
            nodes = proxmox_source_service.fetch_nodes()
            resources = proxmox_source_service.fetch_resources()
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

    return SourcePreviewResponse(
        source_health=source_health,
        nodes=nodes,
        resources=resources,
        token_usage=token_usage,
        gpu_metrics=gpu_metrics,
    )


async def build_analysis(
    placement_request: PlacementRequest | None = None,
) -> AnalysisResponse:
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
    )
    recommendations = aggregation_service.build_recommendations(
        events=events,
        summary=aggregation,
        node_capacities=node_capacities,
        placement=placement,
    )
    summary = aggregation_service.build_summary(
        summary=aggregation,
        placement=placement,
        events=events,
    )

    return AnalysisResponse(
        source_health=preview.source_health,
        aggregation=aggregation,
        features=features,
        events=events,
        recommendations=recommendations,
        summary=summary,
        nodes=preview.nodes,
        resources=preview.resources,
        node_capacities=node_capacities,
        placement=placement,
    )
