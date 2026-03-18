from __future__ import annotations

from app.core.config import settings
from app.schemas import GpuMetricSnapshot, NodeSnapshot, TokenUsageSnapshot


def load_node_snapshots() -> list[NodeSnapshot]:
    nodes: list[NodeSnapshot] = []
    gpu_map = settings.parsed_backend_node_gpu_map
    for item in settings.parsed_nodes_snapshot:
        node_name = str(item.get("node") or "unknown")
        nodes.append(
            NodeSnapshot(
                node=node_name,
                status=str(item.get("status") or "unknown"),
                cpu_ratio=float(item.get("cpu") or 0.0),
                maxcpu=int(item.get("maxcpu") or 0),
                mem_bytes=int(item.get("mem") or 0),
                maxmem_bytes=int(item.get("maxmem") or 0),
                disk_bytes=int(item.get("disk") or 0),
                maxdisk_bytes=int(item.get("maxdisk") or 0),
                uptime=int(item.get("uptime") or 0),
                gpu_count=gpu_map.get(node_name, 0),
            )
        )
    return nodes


def load_token_usage_snapshots() -> list[TokenUsageSnapshot]:
    return [
        TokenUsageSnapshot(
            source=str(item.get("source") or "vllm"),
            window_minutes=int(item.get("window_minutes") or 0),
            requests=int(item.get("requests") or 0),
            prompt_tokens=int(item.get("prompt_tokens") or 0),
            completion_tokens=int(item.get("completion_tokens") or 0),
            total_tokens=int(item.get("total_tokens") or 0),
            growth_ratio=(
                float(item.get("growth_ratio"))
                if item.get("growth_ratio") is not None
                else None
            ),
        )
        for item in settings.parsed_token_usage_snapshots
    ]


def load_gpu_metric_snapshots() -> list[GpuMetricSnapshot]:
    return [
        GpuMetricSnapshot(
            node=str(item.get("node") or "unknown"),
            gpu_count=int(item.get("gpu_count") or 0),
            avg_gpu_utilization=(
                float(item.get("avg_gpu_utilization"))
                if item.get("avg_gpu_utilization") is not None
                else None
            ),
            avg_gpu_memory_ratio=(
                float(item.get("avg_gpu_memory_ratio"))
                if item.get("avg_gpu_memory_ratio") is not None
                else None
            ),
        )
        for item in settings.parsed_gpu_metric_snapshots
    ]
