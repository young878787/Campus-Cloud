from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


HOURS_IN_DAY = 24


class ResourceUsage(BaseModel):
    cpu_cores: float = Field(default=0.0, ge=0.0)
    memory_gb: float = Field(default=0.0, ge=0.0)
    disk_gb: float = Field(default=0.0, ge=0.0)
    gpu_count: float = Field(default=0.0, ge=0.0)


class ResourceShares(BaseModel):
    cpu: float = Field(default=0.0, ge=0.0)
    memory: float = Field(default=0.0, ge=0.0)
    disk: float = Field(default=0.0, ge=0.0)
    gpu: float = Field(default=0.0, ge=0.0)


class VmStackItem(BaseModel):
    name: str
    count: int = Field(default=0, ge=0)


class ReliefSuggestion(BaseModel):
    title: str
    detail: str


class ServerInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    cpu_cores: float = Field(gt=0.0, le=2048.0)
    memory_gb: float = Field(gt=0.0, le=16384.0)
    disk_gb: float = Field(gt=0.0, le=262144.0)
    gpu_count: float = Field(default=0.0, ge=0.0, le=64.0)
    cpu_used: float = Field(default=0.0, ge=0.0)
    memory_used_gb: float = Field(default=0.0, ge=0.0)
    disk_used_gb: float = Field(default=0.0, ge=0.0)
    gpu_used: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_usage(self) -> "ServerInput":
        if self.cpu_used > self.cpu_cores:
            raise ValueError("cpu_used cannot exceed cpu_cores")
        if self.memory_used_gb > self.memory_gb:
            raise ValueError("memory_used_gb cannot exceed memory_gb")
        if self.disk_used_gb > self.disk_gb:
            raise ValueError("disk_used_gb cannot exceed disk_gb")
        if self.gpu_used > self.gpu_count:
            raise ValueError("gpu_used cannot exceed gpu_count")
        return self


class VMTemplate(BaseModel):
    id: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=60)
    cpu_cores: float = Field(gt=0.0, le=512.0)
    memory_gb: float = Field(gt=0.0, le=4096.0)
    disk_gb: float = Field(gt=0.0, le=65536.0)
    gpu_count: float = Field(default=0.0, ge=0.0, le=16.0)
    active_hours: list[int] = Field(default_factory=lambda: list(range(HOURS_IN_DAY)))
    enabled: bool = True

    @model_validator(mode="after")
    def validate_active_hours(self) -> "VMTemplate":
        if not self.active_hours:
            raise ValueError("active_hours must include at least one hour")
        normalized = sorted(set(self.active_hours))
        if normalized != self.active_hours:
            self.active_hours = normalized
        for hour in self.active_hours:
            if hour < 0 or hour >= HOURS_IN_DAY:
                raise ValueError("active_hours must be between 0 and 23")
        for index in range(1, len(self.active_hours)):
            if self.active_hours[index] != self.active_hours[index - 1] + 1:
                raise ValueError("active_hours must describe one continuous range")
        return self


class SimulationRequest(BaseModel):
    servers: list[ServerInput] = Field(min_length=1, max_length=64)
    vm_templates: list[VMTemplate] = Field(default_factory=list, max_length=128)
    selected_vm_template_id: str | None = None
    allow_rebalance: bool = True
    max_steps: int = Field(default=200, ge=1, le=2000)
    strategy: Literal["dominant_share_min"] = "dominant_share_min"


class ServerSnapshot(BaseModel):
    name: str
    total: ResourceUsage
    used: ResourceUsage
    remaining: ResourceUsage
    shares: ResourceShares
    dominant_share: float = Field(default=0.0, ge=0.0)
    average_share: float = Field(default=0.0, ge=0.0)
    placement_count: int = Field(default=0, ge=0)
    placed_vms: list[str] = Field(default_factory=list)
    vm_stack: list[VmStackItem] = Field(default_factory=list)


class PlacementRecord(BaseModel):
    step: int = Field(ge=1)
    vm_template_id: str
    vm_name: str
    server_name: str
    strategy: str
    dominant_share_after: float = Field(default=0.0, ge=0.0)
    average_share_after: float = Field(default=0.0, ge=0.0)
    shares_after: ResourceShares
    reason: str


class SimulationState(BaseModel):
    step: int = Field(ge=0)
    title: str
    latest_placement: PlacementRecord | None = None
    servers: list[ServerSnapshot]


class SimulationSummary(BaseModel):
    selected_vm_name: str | None = None
    requested_vm_count: int = Field(default=0, ge=0)
    total_placements: int = Field(default=0, ge=0)
    placed_by_vm: dict[str, int] = Field(default_factory=dict)
    placed_by_server: dict[str, int] = Field(default_factory=dict)
    failed_vm_names: list[str] = Field(default_factory=list)
    cluster_shares: ResourceShares
    highest_server_dominant_share: float = Field(default=0.0, ge=0.0)
    recommendation_possible: bool = False
    recommendation_target: str | None = None
    recommendation_reason: str | None = None
    bottleneck_server: str | None = None
    bottleneck_resource: str | None = None
    stop_reason: str
    narrative: str
    relief_actions: list[ReliefSuggestion] = Field(default_factory=list)


class HourlySimulation(BaseModel):
    hour: int = Field(ge=0, lt=HOURS_IN_DAY)
    label: str
    active_vm_names: list[str] = Field(default_factory=list)
    reserved_vm_names: list[str] = Field(default_factory=list)
    placements: list[PlacementRecord] = Field(default_factory=list)
    states: list[SimulationState] = Field(default_factory=list)
    summary: SimulationSummary


class DailySimulationSummary(BaseModel):
    reserved_vm_count: int = Field(default=0, ge=0)
    reservation_slot_count: int = Field(default=0, ge=0)
    active_hours: list[int] = Field(default_factory=list)
    reservations_by_hour: dict[str, int] = Field(default_factory=dict)
    peak_hour: int | None = None
    peak_reservation_count: int = Field(default=0, ge=0)
    unplaced_by_hour: dict[str, list[str]] = Field(default_factory=dict)


class SimulationResponse(BaseModel):
    strategy: str
    hours: list[HourlySimulation]
    summary: DailySimulationSummary


class DefaultScenarioResponse(BaseModel):
    servers: list[ServerInput]
    vm_templates: list[VMTemplate]
    note: str
