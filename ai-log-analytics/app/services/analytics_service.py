from __future__ import annotations

from app.core.config import settings
from app.schemas import AnalysisResponse, SourceHealth, SourcePreviewResponse
from app.services import aggregation_service
from app.services import audit_source_service
from app.services import proxmox_source_service
from app.services import snapshot_source_service


async def build_source_preview(limit_audit_logs: int = 200) -> SourcePreviewResponse:
    nodes = []
    resources = []
    audit_logs = []
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

    if not audit_logs and settings.use_direct_database:
        try:
            audit_logs = audit_source_service.fetch_recent_audit_logs(limit=limit_audit_logs)
            source_health.append(
                SourceHealth(
                    name="audit_db",
                    available=True,
                    mode="direct",
                    detail="Fetched audit logs from PostgreSQL.",
                    record_count=len(audit_logs),
                )
            )
        except Exception as exc:
            source_health.append(
                SourceHealth(
                    name="audit_db",
                    available=False,
                    mode="direct",
                    detail=str(exc),
                    record_count=0,
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
        audit_logs=audit_logs,
        token_usage=token_usage,
        gpu_metrics=gpu_metrics,
    )


async def build_analysis(limit_audit_logs: int = 200) -> AnalysisResponse:
    preview = await build_source_preview(limit_audit_logs=limit_audit_logs)
    aggregation = aggregation_service.build_aggregation_summary(
        nodes=preview.nodes,
        resources=preview.resources,
        audit_logs=preview.audit_logs,
        token_usage=preview.token_usage,
        gpu_metrics=preview.gpu_metrics,
    )
    features = aggregation_service.build_features(aggregation)
    audit_available = any(
        item.name == "audit_db" and item.available
        for item in preview.source_health
    )
    events = aggregation_service.build_events(
        summary=aggregation,
        resources=preview.resources,
        gpu_metrics=preview.gpu_metrics,
        audit_source_available=audit_available,
    )
    recommendations = aggregation_service.build_recommendations(events)
    summary = aggregation_service.build_summary(events, aggregation)

    return AnalysisResponse(
        source_health=preview.source_health,
        aggregation=aggregation,
        features=features,
        events=events,
        recommendations=recommendations,
        summary=summary,
    )
