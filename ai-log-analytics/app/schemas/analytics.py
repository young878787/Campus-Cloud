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


class AuditLogEntry(BaseModel):
    user_id: str | None = None
    user_email: str | None = None
    vmid: int | None = None
    action: str
    details: str = Field(default="")
    created_at: datetime | None = None


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
    recent_window_minutes: int = Field(default=60, ge=0)
    baseline_days: int = Field(default=7, ge=0)
    aggregation_window_minutes: int = Field(default=5, ge=0)
    stair_coefficient: float = Field(default=1.0, ge=1.0)
    node_count: int = Field(default=0, ge=0)
    resource_count: int = Field(default=0, ge=0)
    audit_log_count: int = Field(default=0, ge=0)
    total_cpu_capacity: int = Field(default=0, ge=0)
    avg_node_cpu_ratio: float = Field(default=0.0, ge=0.0)
    avg_node_memory_ratio: float = Field(default=0.0, ge=0.0)
    avg_resource_cpu_ratio: float = Field(default=0.0, ge=0.0)
    avg_resource_memory_ratio: float = Field(default=0.0, ge=0.0)
    gpu_count: int = Field(default=0, ge=0)
    avg_gpu_utilization: float | None = Field(default=None, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    token_requests: int = Field(default=0, ge=0)
    token_growth_ratio: float | None = Field(default=None, ge=0.0)


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


class SourcePreviewResponse(BaseModel):
    source_health: list[SourceHealth]
    nodes: list[NodeSnapshot] = Field(default_factory=list)
    resources: list[ResourceSnapshot] = Field(default_factory=list)
    audit_logs: list[AuditLogEntry] = Field(default_factory=list)
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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ExplainRequest(BaseModel):
    question: str | None = Field(default=None)
    history: list[ChatMessage] = Field(default_factory=list)
    limit_audit_logs: int = Field(default=200, ge=1, le=1000)
    max_tokens: int = Field(default=800, ge=128, le=4000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class ExplainResponse(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    answer: str
    ai_used: bool = False
    model: str | None = None
    analysis: AnalysisResponse
    warning: str | None = None
