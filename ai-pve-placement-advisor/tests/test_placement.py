from __future__ import annotations

import os

os.environ.setdefault("VLLM_TIMEOUT", "300")

from app.schemas import NodeSnapshot, PlacementRequest, ResourceSnapshot
from app.services.aggregation_service import (
    build_node_capacities,
    build_placement_recommendation,
)


def _make_node(
    *,
    name: str,
    cpu_ratio: float,
    maxcpu: int,
    mem_used_gib: int,
    mem_total_gib: int,
    disk_used_gib: int,
    disk_total_gib: int,
    gpu_count: int = 0,
) -> NodeSnapshot:
    gib = 1024**3
    return NodeSnapshot(
        node=name,
        status="online",
        cpu_ratio=cpu_ratio,
        maxcpu=maxcpu,
        mem_bytes=mem_used_gib * gib,
        maxmem_bytes=mem_total_gib * gib,
        disk_bytes=disk_used_gib * gib,
        maxdisk_bytes=disk_total_gib * gib,
        gpu_count=gpu_count,
    )


def _make_resource(*, node: str, status: str = "running") -> ResourceSnapshot:
    return ResourceSnapshot(
        vmid=1,
        name="vm",
        resource_type="qemu",
        node=node,
        status=status,
        cpu_ratio=0.1,
        maxcpu=2,
        mem_bytes=1024**3,
        maxmem_bytes=2 * 1024**3,
        disk_bytes=10 * 1024**3,
        maxdisk_bytes=20 * 1024**3,
    )


def test_full_fit_single_node():
    node = _make_node(
        name="pve-a",
        cpu_ratio=0.2,
        maxcpu=16,
        mem_used_gib=8,
        mem_total_gib=64,
        disk_used_gib=100,
        disk_total_gib=500,
    )
    capacities = build_node_capacities(nodes=[node], resources=[])

    request = PlacementRequest(
        machine_name="class-vm",
        resource_type="vm",
        cores=2,
        memory_mb=4096,
        disk_gb=20,
        instance_count=3,
    )
    result = build_placement_recommendation(request=request, node_capacities=capacities)

    assert result.feasible is True
    assert result.assigned_instances == 3
    assert result.unassigned_instances == 0


def test_partial_fit_when_capacity_limited():
    node = _make_node(
        name="pve-a",
        cpu_ratio=0.7,
        maxcpu=8,
        mem_used_gib=26,
        mem_total_gib=32,
        disk_used_gib=160,
        disk_total_gib=200,
    )
    capacities = build_node_capacities(nodes=[node], resources=[])

    request = PlacementRequest(
        machine_name="heavy-vm",
        resource_type="vm",
        cores=2,
        memory_mb=2048,
        disk_gb=10,
        instance_count=3,
    )
    result = build_placement_recommendation(request=request, node_capacities=capacities)

    assert result.feasible is False
    assert result.assigned_instances < 3
    assert result.unassigned_instances > 0


def test_running_only_guest_count():
    node = _make_node(
        name="pve-a",
        cpu_ratio=0.2,
        maxcpu=8,
        mem_used_gib=8,
        mem_total_gib=32,
        disk_used_gib=50,
        disk_total_gib=200,
    )
    resources = [
        _make_resource(node="pve-a", status="running"),
        _make_resource(node="pve-a", status="stopped"),
    ]

    capacities = build_node_capacities(nodes=[node], resources=resources)

    assert capacities[0].running_resources == 1


def test_gpu_requirement_filters_nodes():
    nodes = [
        _make_node(
            name="pve-cpu",
            cpu_ratio=0.1,
            maxcpu=16,
            mem_used_gib=8,
            mem_total_gib=64,
            disk_used_gib=100,
            disk_total_gib=500,
            gpu_count=0,
        ),
        _make_node(
            name="pve-gpu",
            cpu_ratio=0.2,
            maxcpu=16,
            mem_used_gib=8,
            mem_total_gib=64,
            disk_used_gib=100,
            disk_total_gib=500,
            gpu_count=2,
        ),
    ]
    capacities = build_node_capacities(nodes=nodes, resources=[])

    request = PlacementRequest(
        machine_name="gpu-vm",
        resource_type="vm",
        cores=2,
        memory_mb=4096,
        disk_gb=20,
        gpu_required=1,
        instance_count=1,
    )
    result = build_placement_recommendation(request=request, node_capacities=capacities)

    assert result.feasible is True
    assert len(result.placements) == 1
    assert result.placements[0].node == "pve-gpu"
