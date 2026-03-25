from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class PlacementRequest(BaseModel):
    machine_name: str = Field(default="custom workload", min_length=1, max_length=80)
    resource_type: str = Field(default="vm", min_length=1, max_length=20)
    cores: int = Field(default=2, ge=1, le=256)
    memory_mb: int = Field(default=2048, ge=128, le=1048576)
    disk_gb: int = Field(default=20, ge=1, le=65536)
    gpu_required: int = Field(default=0, ge=0, le=16)
    instance_count: int = Field(default=1, ge=1, le=100)
    estimated_users_per_instance: int = Field(default=0, ge=0, le=1000000)


class AiMetrics(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    tokens_per_second: float = Field(default=0.0, ge=0.0)


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


class BackendTrafficSnapshot(BaseModel):
    sample_size: int = Field(default=0, ge=0)
    window_minutes: int = Field(default=60, ge=1)
    submitted_in_window: int = Field(default=0, ge=0)
    pending_total: int = Field(default=0, ge=0)
    approved_total: int = Field(default=0, ge=0)
    requested_cpu_cores_total: int = Field(default=0, ge=0)
    requested_memory_mb_total: int = Field(default=0, ge=0)
    requested_disk_gb_total: int = Field(default=0, ge=0)


class AuditSignalSnapshot(BaseModel):
    sample_size: int = Field(default=0, ge=0)
    window_minutes: int = Field(default=60, ge=1)
    recent_total: int = Field(default=0, ge=0)
    create_events: int = Field(default=0, ge=0)
    start_events: int = Field(default=0, ge=0)
    stop_events: int = Field(default=0, ge=0)
    delete_events: int = Field(default=0, ge=0)
    review_events: int = Field(default=0, ge=0)


class NodeCapacity(BaseModel):
    node: str
    status: str
    gpu_count: int = Field(default=0, ge=0)
    running_resources: int = Field(default=0, ge=0)
    guest_soft_limit: int = Field(default=0, ge=0)
    guest_pressure_ratio: float = Field(default=0.0, ge=0.0)
    guest_overloaded: bool = False
    candidate: bool = True
    cpu_ratio: float = Field(default=0.0, ge=0.0)
    memory_ratio: float = Field(default=0.0, ge=0.0)
    disk_ratio: float = Field(default=0.0, ge=0.0)
    total_cpu_cores: float = Field(default=0.0, ge=0.0)
    allocatable_cpu_cores: float = Field(default=0.0, ge=0.0)
    total_memory_bytes: int = Field(default=0, ge=0)
    allocatable_memory_bytes: int = Field(default=0, ge=0)
    total_disk_bytes: int = Field(default=0, ge=0)
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


class PlacementPlan(BaseModel):
    feasible: bool = False
    assigned_instances: int = Field(default=0, ge=0)
    unassigned_instances: int = Field(default=0, ge=0)
    effective_cpu_cores_per_instance: float = Field(default=0.0, ge=0.0)
    effective_memory_bytes_per_instance: int = Field(default=0, ge=0)
    recommended_node: str | None = None
    summary: str
    rationale: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    placements: list[PlacementDecision] = Field(default_factory=list)
    candidate_nodes: list[NodeCapacity] = Field(default_factory=list)


class SuggestedAction(BaseModel):
    kind: str = Field(default="provision_on_node")
    execute_now: bool = False
    node: str | None = None
    resource_type: str
    instance_count: int = Field(default=1, ge=1)


class PlacementAdvisorResponse(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reply: str
    ai_used: bool = False
    model: str | None = None
    warning: str | None = None
    ai_metrics: AiMetrics | None = None
    request: PlacementRequest
    placement: PlacementPlan
    suggested_action: SuggestedAction | None = None
    backend_traffic: BackendTrafficSnapshot | None = None
    audit_signals: AuditSignalSnapshot | None = None
    node_capacities: list[NodeCapacity] = Field(default_factory=list)
