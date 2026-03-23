from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.schemas.recommendation import DeviceNode
from app.schemas.resource import NodeSchema


async def fetch_backend_node_payload(_: str | None = None) -> list[dict]:
    if not settings.use_internal_nodes_api:
        return []
    return settings.parsed_nodes_snapshot


def normalize_node_payload(payload: list[dict]) -> list[DeviceNode]:
    gpu_map = settings.parsed_backend_node_gpu_map
    nodes: list[DeviceNode] = []
    for item in payload:
        maxmem = int(item.get("maxmem") or 0)
        mem = int(item.get("mem") or 0)
        nodes.append(
            DeviceNode(
                node=str(item.get("node") or "unknown"),
                maxcpu=int(item.get("maxcpu") or 0),
                cpu_usage_ratio=float(item.get("cpu") or 0.0),
                maxmem_gb=round(maxmem / (1024**3), 2) if maxmem else 0.0,
                mem_usage_ratio=(mem / maxmem) if maxmem else 0.0,
                gpu_count=gpu_map.get(str(item.get("node") or "unknown"), 0),
            )
        )
    return nodes


def to_public_node_schema(payload: list[dict[str, Any]]) -> list[NodeSchema]:
    return [
        NodeSchema(
            node=str(item.get("node") or "unknown"),
            status=str(item.get("status") or "online"),
            cpu=float(item.get("cpu") or 0.0),
            maxcpu=int(item.get("maxcpu") or 0),
            mem=int(item.get("mem") or 0),
            maxmem=int(item.get("maxmem") or 0),
            uptime=int(item.get("uptime") or 0),
        )
        for item in payload
    ]


def summarize_device_nodes(nodes: list[DeviceNode]) -> dict[str, Any]:
    total_cpu = 0
    total_memory_gb = 0.0
    total_gpu = 0
    summarized_nodes: list[dict[str, Any]] = []
    for node in nodes:
        free_cpu = max(int(round(node.maxcpu * (1 - node.cpu_usage_ratio))), 0)
        free_memory_gb = round(max(node.maxmem_gb * (1 - node.mem_usage_ratio), 0.0), 2)
        summarized_nodes.append(
            {
                "node": node.node,
                "free_cpu": free_cpu,
                "free_memory_gb": free_memory_gb,
                "gpu_count": node.gpu_count,
            }
        )
        total_cpu += free_cpu
        total_memory_gb += free_memory_gb
        total_gpu += node.gpu_count

    return {
        "nodes": summarized_nodes,
        "free_cpu": total_cpu,
        "free_memory_gb": round(total_memory_gb, 2),
        "gpu_count": total_gpu,
    }
