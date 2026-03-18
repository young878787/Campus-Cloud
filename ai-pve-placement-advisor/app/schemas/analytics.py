from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class NodeSnapshot(BaseModel):
    node: str
    status: str = Field(default="unknown")
    cpu_ratio: float = Field(default=0.0, ge=0.0)
    maxcpu: int = Field(default=0, ge=0)
    mem_bytes: int = Field(default=0, ge=0)
    maxmem_bytes: int = Field(default=0, ge=0)
    disk_bytes: int = Field(default=0, ge=0)
    maxdisk_bytes: int = Field(default=0, ge=0)
    uptime: int | None = Field(default=None, ge=0)
    gpu_count: int = Field(default=0, ge=0)


class ResourceSnapshot(BaseModel):
    vmid: int
    name: str = Field(default="")
    resource_type: str = Field(default="unknown")
    node: str = Field(default="unknown")
    status: str = Field(default="unknown")
    cpu_ratio: float = Field(default=0.0, ge=0.0)
    maxcpu: int = Field(default=0, ge=0)
    mem_bytes: int = Field(default=0, ge=0)
    maxmem_bytes: int = Field(default=0, ge=0)
    disk_bytes: int = Field(default=0, ge=0)
    maxdisk_bytes: int = Field(default=0, ge=0)
    uptime: int | None = Field(default=None, ge=0)


class TokenUsageSnapshot(BaseModel):
    source: str = Field(default="vllm")
    window_minutes: int = Field(default=0, ge=0)
    requests: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    growth_ratio: float | None = Field(default=None, ge=0.0)


class GpuMetricSnapshot(BaseModel):
    node: str = Field(default="unknown")
    gpu_count: int = Field(default=0, ge=0)
    avg_gpu_utilization: float | None = Field(default=None, ge=0.0, le=100.0)
    avg_gpu_memory_ratio: float | None = Field(default=None, ge=0.0, le=1.5)


class SourceHealth(BaseModel):
    name: str
    available: bool
    mode: str
    detail: str = Field(default="")
    record_count: int = Field(default=0, ge=0)


class AggregationSummary(BaseModel):
    stair_coefficient: float = Field(default=1.0, ge=1.0)
    node_count: int = Field(default=0, ge=0)
    resource_count: int = Field(default=0, ge=0)
    total_cpu_capacity: int = Field(default=0, ge=0)
    total_memory_bytes: int = Field(default=0, ge=0)
    total_disk_bytes: int = Field(default=0, ge=0)
    available_cpu_cores: float = Field(default=0.0, ge=0.0)
    available_memory_bytes: int = Field(default=0, ge=0)
    available_disk_bytes: int = Field(default=0, ge=0)
    avg_node_cpu_ratio: float = Field(default=0.0, ge=0.0)
    avg_node_memory_ratio: float = Field(default=0.0, ge=0.0)
    avg_node_disk_ratio: float = Field(default=0.0, ge=0.0)
    avg_guest_pressure_ratio: float = Field(default=0.0, ge=0.0)
    guest_overloaded_node_count: int = Field(default=0, ge=0)
    cluster_health: str = Field(default="unknown")


class FeatureItem(BaseModel):
    key: str
    value: float | int | str | bool | None
    description: str = Field(default="")


class EventItem(BaseModel):
    code: str
    severity: str
    score: int = Field(default=1, ge=1, le=5)
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecommendationItem(BaseModel):
    target: str
    action: str
    reason: str


class PlacementRequest(BaseModel):
    machine_name: str = Field(default="custom workload", min_length=1, max_length=80)
    resource_type: str = Field(default="vm", min_length=1, max_length=20)
    cores: int = Field(default=2, ge=1, le=256)
    memory_mb: int = Field(default=2048, ge=128, le=1048576)
    disk_gb: int = Field(default=20, ge=1, le=65536)
    instance_count: int = Field(default=1, ge=1, le=100)
    estimated_users_per_instance: int = Field(default=0, ge=0, le=1000000)


class NodeCapacity(BaseModel):
    node: str
    status: str
    running_resources: int = Field(default=0, ge=0)
    guest_soft_limit: int = Field(default=0, ge=0)
    guest_pressure_ratio: float = Field(default=0.0, ge=0.0)
    guest_overloaded: bool = False
    candidate: bool = True
    cpu_ratio: float = Field(default=0.0, ge=0.0)
    memory_ratio: float = Field(default=0.0, ge=0.0)
    disk_ratio: float = Field(default=0.0, ge=0.0)
    total_cpu_cores: float = Field(default=0.0, ge=0.0)
    used_cpu_cores: float = Field(default=0.0, ge=0.0)
    raw_available_cpu_cores: float = Field(default=0.0, ge=0.0)
    allocatable_cpu_cores: float = Field(default=0.0, ge=0.0)
    total_memory_bytes: int = Field(default=0, ge=0)
    used_memory_bytes: int = Field(default=0, ge=0)
    raw_available_memory_bytes: int = Field(default=0, ge=0)
    allocatable_memory_bytes: int = Field(default=0, ge=0)
    total_disk_bytes: int = Field(default=0, ge=0)
    used_disk_bytes: int = Field(default=0, ge=0)
    raw_available_disk_bytes: int = Field(default=0, ge=0)
    allocatable_disk_bytes: int = Field(default=0, ge=0)


class PlacementDecision(BaseModel):
    node: str
    instance_count: int = Field(default=0, ge=0)
    cpu_cores_reserved: float = Field(default=0.0, ge=0.0)
    memory_bytes_reserved: int = Field(default=0, ge=0)
    disk_bytes_reserved: int = Field(default=0, ge=0)
    remaining_cpu_cores: float = Field(default=0.0, ge=0.0)
    remaining_memory_bytes: int = Field(default=0, ge=0)
    remaining_disk_bytes: int = Field(default=0, ge=0)


class PlacementRecommendation(BaseModel):
    request: PlacementRequest
    feasible: bool = False
    assigned_instances: int = Field(default=0, ge=0)
    unassigned_instances: int = Field(default=0, ge=0)
    effective_cpu_cores_per_instance: float = Field(default=0.0, ge=0.0)
    effective_memory_bytes_per_instance: int = Field(default=0, ge=0)
    user_pressure_level: str = Field(default="none")
    summary: str
    rationale: list[str] = Field(default_factory=list)
    placements: list[PlacementDecision] = Field(default_factory=list)
    candidate_nodes: list[NodeCapacity] = Field(default_factory=list)


class SourcePreviewResponse(BaseModel):
    source_health: list[SourceHealth]
    nodes: list[NodeSnapshot] = Field(default_factory=list)
    resources: list[ResourceSnapshot] = Field(default_factory=list)
    token_usage: list[TokenUsageSnapshot] = Field(default_factory=list)
    gpu_metrics: list[GpuMetricSnapshot] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_health: list[SourceHealth]
    aggregation: AggregationSummary
    features: list[FeatureItem]
    events: list[EventItem]
    recommendations: list[RecommendationItem]
    summary: str
    nodes: list[NodeSnapshot] = Field(default_factory=list)
    resources: list[ResourceSnapshot] = Field(default_factory=list)
    node_capacities: list[NodeCapacity] = Field(default_factory=list)
    placement: PlacementRecommendation | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ExplainRequest(BaseModel):
    question: str | None = Field(default=None)
    history: list[ChatMessage] = Field(default_factory=list)
    placement_request: PlacementRequest | None = None
    max_tokens: int = Field(default=800, ge=128, le=4000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class ExplainResponse(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    answer: str
    ai_used: bool = False
    model: str | None = None
    analysis: AnalysisResponse
    warning: str | None = None
