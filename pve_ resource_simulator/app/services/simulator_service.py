from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import mean

from app.schemas import (
    DailySimulationSummary,
    DefaultScenarioResponse,
    HistoricalProfile,
    HOURS_IN_DAY,
    HourlySimulation,
    PlacementRecord,
    ReliefSuggestion,
    ResourceShares,
    ResourceUsage,
    ServerInput,
    ServerSnapshot,
    SimulationRequest,
    SimulationCalculationRow,
    SimulationResponse,
    SimulationState,
    SimulationSummary,
    StorageInfo,
    VMTemplate,
    VmStackItem,
)
from app.services import proxmox_analytics_service


EPSILON = 1e-9  # 浮點數比較用的極小容忍值，避免邊界誤差。
CPU_OVERCOMMIT_RATIO = 2.0  # CPU 的 policy 容量 = 實體 CPU * 這個倍率；代表 placement 允許 CPU overcommit。
RAM_USABLE_RATIO = 0.9  # 只有這個比例的實體 RAM 會被視為可分配，保留一部分安全緩衝。
CPU_SAFE_SHARE = 0.7  # 實體 CPU share 低於這個值時，不加 CPU contention penalty。
CPU_MAX_SHARE = 1.2  # 實體 CPU share 高於這個值時，CPU contention penalty 視為滿額。
DISK_SAFE_SHARE = 0.75  # Disk share 低於這個值時，不加 disk contention penalty。
DISK_MAX_SHARE = 0.95  # Disk share 高於這個值時，disk contention penalty 視為滿額。
CPU_SHARE_WEIGHT = 1.0  # CPU share 在 dominant-share scoring 裡的權重。
MEMORY_SHARE_WEIGHT = 1.2  # RAM share 的權重；記憶體壓力比 CPU 更敏感，所以略高。
DISK_SHARE_WEIGHT = 1.5  # Disk share 的權重；磁碟越接近滿載，應越早降低優先權。
GPU_SHARE_WEIGHT = 3.0  # GPU share 的權重；GPU 稀缺，所以不平衡要重罰。
CPU_CONTENTION_WEIGHT = 2.0  # CPU contention penalty 在最終 placement score 裡的倍率。
MEMORY_OVERFLOW_WEIGHT = 5.0  # RAM 超過 policy 容量時的重罰倍率。
DISK_CONTENTION_WEIGHT = 1.5  # Disk contention penalty 在最終 placement score 裡的倍率。
MIGRATION_COST = 0.15  # rebalance 搬移時額外加上的成本，表示搬移有代價但不是完全不能做。
LOCAL_REBALANCE_MAX_MOVES = 2  # local rebalance 最多只搜尋這麼多次搬移，保持小範圍且可解釋。
CPU_MARGIN = 1.4  # 用歷史 CPU ratio 估 baseline demand 時乘上的安全倍率。
RAM_MARGIN = 1.15  # 用歷史 RAM ratio 估 baseline demand 時乘上的安全倍率。
CPU_FLOOR_RATIO = 0.35  # baseline CPU demand 最低不會低於申請 CPU 的這個比例。
RAM_FLOOR_RATIO = 0.5  # baseline RAM demand 最低不會低於申請 RAM 的這個比例。
CPU_PEAK_MARGIN = 1.1  # 用歷史 peak CPU ratio 估 peak risk 時再加上的保守倍率。
RAM_PEAK_MARGIN = 1.05  # 用歷史 peak RAM ratio 估 peak risk 時再加上的保守倍率。
CPU_PEAK_WARN_SHARE = CPU_SAFE_SHARE  # CPU peak-risk 的 warning 門檻。
CPU_PEAK_HIGH_SHARE = CPU_MAX_SHARE  # CPU peak-risk 的 high 門檻。
RAM_PEAK_WARN_SHARE = 0.8  # RAM peak-risk 的 warning 門檻。
RAM_PEAK_HIGH_SHARE = 0.85  # RAM peak-risk 的 high 門檻。
LOADAVG_WARN_PER_CORE = 0.8  # 每核心 loadavg 到這個程度後，host 會開始被降權。
LOADAVG_MAX_PER_CORE = 1.5  # 每核心 loadavg 到這個程度後，loadavg penalty 視為滿額。
LOADAVG_PENALTY_WEIGHT = 0.9  # loadavg soft penalty 的倍率；只降低優先權，不直接 hard reject。

LXC_DEFAULT_CPU_RATIO = 0.45
LXC_DEFAULT_MEMORY_RATIO = 0.55
LXC_CPU_MARGIN = 1.2
LXC_RAM_MARGIN = 1.05
LXC_CPU_FLOOR_RATIO = 0.25
LXC_RAM_FLOOR_RATIO = 0.35
LXC_CPU_PEAK_MARGIN = 1.05
LXC_RAM_PEAK_MARGIN = 1.02


_SPEED_RANK: dict[str, int] = {"nvme": 0, "ssd": 1, "hdd": 2, "unknown": 3}


@dataclass
class _StorageState:
    """Mutable per-placement-run snapshot of a single storage pool."""
    storage: str
    can_vm: bool
    can_lxc: bool
    can_iso: bool
    can_backup: bool
    is_shared: bool
    speed_tier: str   # "nvme" | "ssd" | "hdd" | "unknown"
    user_priority: int  # 1-10, lower = more preferred
    total_gb: float
    avail_gb: float   # decreases as VMs are placed onto this pool
    active: bool
    enabled: bool     # user toggle — False = excluded from placement
    placed_count: int = 0              # total VMs placed on this pool (normal placements)
    # Overcommit tracking (disk_overcommit_ratio > 1.0 only)
    overcommit_avail_gb: float = 0.0   # extra allocatable space beyond physical avail_gb
    overcommit_placed_count: int = 0   # number of VMs placed via overcommit on this pool


@dataclass
class _PlacedVm:
    template_id: str
    template: VMTemplate
    storage_pool: str | None = None    # name of the pool used for disk
    is_cpu_overcommit: bool = False    # True when CPU placement exceeded physical cores
    is_overcommit: bool = False        # True when disk placement consumed overcommit capacity
    overcommit_disk_gb: float = 0.0    # how many GB were taken from the overcommit bucket


@dataclass
class _WorkingServer:
    name: str
    total_cpu: float
    total_memory: float
    total_disk: float
    total_gpu: float
    used_cpu: float
    used_memory: float
    used_disk: float
    used_gpu: float
    current_loadavg_1: float | None = None
    average_loadavg_1: float | None = None
    priority: int = 5
    cpu_overcommit_ratio: float = CPU_OVERCOMMIT_RATIO
    storage_pools: list[_StorageState] = field(default_factory=list)
    placed_vms: list[_PlacedVm] = field(default_factory=list)

    @property
    def placement_count(self) -> int:
        return len(self.placed_vms)


def build_default_scenario() -> DefaultScenarioResponse:
    return DefaultScenarioResponse(
        servers=[
            ServerInput(
                name="pve-a",
                cpu_cores=24,
                memory_gb=96,
                disk_gb=1200,
                gpu_count=0,
                cpu_used=0,
                memory_used_gb=0,
                disk_used_gb=0,
                gpu_used=0,
                priority=1,
            ),
            ServerInput(
                name="pve-b",
                cpu_cores=16,
                memory_gb=64,
                disk_gb=900,
                gpu_count=0,
                cpu_used=0,
                memory_used_gb=0,
                disk_used_gb=0,
                gpu_used=0,
                priority=3,
            ),
            ServerInput(
                name="pve-c",
                cpu_cores=32,
                memory_gb=128,
                disk_gb=1600,
                gpu_count=0,
                cpu_used=0,
                memory_used_gb=0,
                disk_used_gb=0,
                gpu_used=0,
                priority=5,
            ),
        ],
        vm_templates=[],
        note=(
            "Default scenario starts with three empty PVE nodes and no VMs. "
            "Add VM reservations, mark their hourly windows, and review placement "
            "hour by hour across the day."
        ),
        source="default",
        historical_profiles=[],
        historical_peak_hours=[],
        historical_hourly_peaks={},
    )


async def build_live_scenario() -> DefaultScenarioResponse:
    analytics = await proxmox_analytics_service.fetch_monthly_analytics()
    servers = []
    for node in analytics.nodes:
        if node.status != "online":
            continue
        if node.total_cpu_cores is None or node.total_memory_gb is None:
            continue
        # Only count LOCAL VM-compatible pools for node disk budget.
        # Shared pools (NFS, Ceph, RBD …) are counted once in the simulator
        # via shared pool registry, not per-node.
        local_vm_storages = [
            s for s in node.storages if s.active and (s.can_vm or s.can_lxc) and not s.is_shared
        ]
        any_vm_storages = [s for s in node.storages if s.active and (s.can_vm or s.can_lxc)]
        if local_vm_storages:
            disk_total = sum(s.total_gb for s in local_vm_storages)
            disk_used = sum(s.used_gb for s in local_vm_storages)
        elif any_vm_storages:
            # All storage is shared — use the first node's shared pool capacity as fallback
            disk_total = sum(s.total_gb for s in any_vm_storages)
            disk_used = sum(s.used_gb for s in any_vm_storages)
        elif node.total_disk_gb is not None:
            disk_total = node.total_disk_gb
            disk_used = (node.total_disk_gb or 0.0) * (node.current_disk_ratio or 0.0)
        else:
            continue
        servers.append(
            ServerInput(
                name=node.name,
                cpu_cores=node.total_cpu_cores,
                memory_gb=node.total_memory_gb,
                disk_gb=disk_total,
                gpu_count=0,
                cpu_used=(node.total_cpu_cores or 0.0) * (node.current_cpu_ratio or 0.0),
                memory_used_gb=(node.total_memory_gb or 0.0) * (node.current_memory_ratio or 0.0),
                disk_used_gb=disk_used,
                gpu_used=0,
                current_loadavg_1=(node.current_loadavg[0] if node.current_loadavg else None),
                average_loadavg_1=node.average_loadavg_1,
                storages=node.storages,
            )
        )
    if not servers:
        raise proxmox_analytics_service.ProxmoxAnalyticsError(
            "No online Proxmox nodes could be converted into a live simulator scenario."
        )

    return DefaultScenarioResponse(
        servers=servers,
        vm_templates=[],
        note=(
            f"Live PVE scenario from {analytics.host}. "
            "Current node usage is loaded from Proxmox, and new reservations use "
            "historical same-type CPU/RAM weighted mean baselines and P95 peaks when available."
        ),
        source="live",
        historical_profiles=proxmox_analytics_service.build_historical_profiles(
            analytics.guest_types
        ),
        historical_peak_hours=_cluster_peak_hours(analytics.cluster.hourly),
        historical_hourly_peaks=_cluster_hourly_peak_values(analytics.cluster.hourly),
    )


def run_simulation(request: SimulationRequest) -> SimulationResponse:
    enabled_templates = [template for template in request.vm_templates if template.enabled]
    hourly_results = [
        _run_hour_simulation(
            hour=hour,
            request=request,
            enabled_templates=enabled_templates,
        )
        for hour in range(HOURS_IN_DAY)
    ]
    return SimulationResponse(
        strategy=request.strategy,
        hours=hourly_results,
        summary=_build_daily_summary(enabled_templates, hourly_results),
    )


def _run_hour_simulation(
    *,
    hour: int,
    request: SimulationRequest,
    enabled_templates: list[VMTemplate],
) -> HourlySimulation:
    hour_templates = [template for template in enabled_templates if hour in template.active_hours]
    if request.selected_vm_template_id is not None and not any(
        template.id == request.selected_vm_template_id for template in hour_templates
    ):
        requested_templates = []
    else:
        requested_templates = _resolve_requested_templates(
            selected_vm_template_id=request.selected_vm_template_id,
            enabled_templates=hour_templates,
        )
    expanded_requested_templates = _expand_templates(
        templates=requested_templates,
        max_instances=request.max_steps,
    )
    effective_template_results = [
        _effective_template_for_hour(
            template=template,
            hour=hour,
            historical_profiles=request.historical_profiles,
        )
        for template in expanded_requested_templates
    ]
    effective_requested_templates = [item["template"] for item in effective_template_results]
    calculations = [
        SimulationCalculationRow(
            vm_template_id=item["requested"].id,
            vm_name=item["requested"].name,
            requested_cpu_cores=round(item["requested"].cpu_cores, 2),
            requested_memory_gb=round(item["requested"].memory_gb, 2),
            requested_disk_gb=round(item["requested"].disk_gb, 2),
            effective_cpu_cores=round(item["template"].cpu_cores, 2),
            effective_memory_gb=round(item["template"].memory_gb, 2),
            peak_cpu_cores=round(item["peak_template"].cpu_cores, 2),
            peak_memory_gb=round(item["peak_template"].memory_gb, 2),
            source=item["source"],
            profile_label=item["profile_label"],
            cpu_ratio=item["cpu_ratio"],
            memory_ratio=item["memory_ratio"],
            placement_status="pending",
            peak_risk="pending",
        )
        for item in effective_template_results
    ]
    servers = _build_servers(
        request.servers,
        cpu_overcommit_ratio=request.cpu_overcommit_ratio,
        disk_overcommit_ratio=request.disk_overcommit_ratio,
    )
    placements: list[PlacementRecord] = []
    failed_templates: list[VMTemplate] = []
    states: list[SimulationState] = [
        SimulationState(
            step=0,
            title=f"{_hour_label(hour)} initial state",
            latest_placement=None,
            servers=_snapshot_servers(servers),
        )
    ]

    if not expanded_requested_templates:
        final_servers = _snapshot_servers(servers)
        summary = _build_summary(
            final_servers=final_servers,
            placements=[],
            stop_reason=f"No reservations in {_hour_label(hour)}.",
            enabled_templates=requested_templates,
            requested_templates=expanded_requested_templates,
            failed_templates=[],
        )
        return HourlySimulation(
            hour=hour,
            label=_hour_label(hour),
            active_vm_names=[],
            reserved_vm_names=_template_names_with_count(enabled_templates),
            calculations=[],
            placements=[],
            states=states,
            summary=summary,
        )

    use_node_priority = request.strategy == "priority_dominant_share"
    assignment_map: dict[str, str] = {}
    final_servers = _snapshot_servers(servers)
    for index, template in enumerate(effective_requested_templates, start=1):
        previous_assignments = dict(assignment_map)
        server_name = _place_template(
            servers=servers,
            template=template,
            allow_rebalance=request.allow_rebalance,
            assignment_map=assignment_map,
            use_node_priority=use_node_priority,
        )
        final_servers = _snapshot_servers(servers)

        if server_name is not None:
            placed_server = _server_by_name(servers, server_name)
            placed_pv = next(
                (pv for pv in reversed(placed_server.placed_vms)
                 if pv.template_id == template.id),
                None,
            )
            _update_calculation_row(
                calculations=calculations,
                vm_template_id=template.id,
                placed_server_name=server_name,
                placement_status="placed",
                placed_storage_pool=placed_pv.storage_pool if placed_pv else None,
                is_cpu_overcommit=placed_pv.is_cpu_overcommit if placed_pv else False,
                is_disk_overcommit=placed_pv.is_overcommit if placed_pv else False,
            )
            placement = PlacementRecord(
                step=index,
                vm_template_id=template.id,
                vm_name=template.name,
                server_name=server_name,
                strategy=request.strategy,
                dominant_share_after=round(
                    _snapshot_dominant_share(final_servers, server_name),
                    4,
                ),
                average_share_after=round(
                    _snapshot_average_share(final_servers, server_name),
                    4,
                ),
                shares_after=_snapshot_server_shares(final_servers, server_name),
                reason=_build_rebalance_reason(
                    template=template,
                    server_name=server_name,
                    server=_server_by_name(servers, server_name),
                    previous_assignments=previous_assignments,
                    current_assignments=assignment_map,
                ),
            )
            placements.append(placement)
            states.append(
                SimulationState(
                    step=index,
                    title=f"Add {template.name} -> {server_name}",
                    latest_placement=placement,
                    servers=final_servers,
                )
            )
        else:
            failed_templates.append(template)
            _update_calculation_row(
                calculations=calculations,
                vm_template_id=template.id,
                placed_server_name=None,
                placement_status="no_fit",
            )
            states.append(
                SimulationState(
                    step=index,
                    title=f"Add {template.name} -> no fit",
                    latest_placement=None,
                    servers=final_servers,
                )
            )

    if not placements and failed_templates:
        stop_reason = "No server can fit the active reservations in this hour."
    elif failed_templates:
        stop_reason = (
            f"Placed {len(effective_requested_templates) - len(failed_templates)} / {len(effective_requested_templates)} active VMs. "
            f"Unplaced: {', '.join(template.name for template in failed_templates)}."
        )
    else:
        stop_reason = f"Placed all {len(effective_requested_templates)} active VMs."

    summary = _build_summary(
        final_servers=final_servers,
        placements=[item for item in placements if item.step <= len(effective_requested_templates)],
        stop_reason=stop_reason,
        enabled_templates=effective_requested_templates,
        requested_templates=effective_requested_templates,
        failed_templates=failed_templates,
    )
    _reconcile_calculations(
        calculations=calculations,
        final_assignment_map=assignment_map,
        final_servers=final_servers,
    )
    return HourlySimulation(
        hour=hour,
        label=_hour_label(hour),
        active_vm_names=[template.name for template in effective_requested_templates],
        reserved_vm_names=_template_names_with_count(enabled_templates),
        calculations=calculations,
        placements=placements,
        states=states,
        summary=summary,
    )


def _build_daily_summary(
    enabled_templates: list[VMTemplate],
    hourly_results: list[HourlySimulation],
) -> DailySimulationSummary:
    reservations_by_hour = {
        str(hour): sum(template.count for template in enabled_templates if hour in template.active_hours)
        for hour in range(HOURS_IN_DAY)
    }
    active_hours = [hour for hour in range(HOURS_IN_DAY) if reservations_by_hour[str(hour)] > 0]
    peak_hour = max(
        range(HOURS_IN_DAY),
        key=lambda hour: reservations_by_hour[str(hour)],
        default=0,
    )
    peak_count = reservations_by_hour[str(peak_hour)] if enabled_templates else 0
    return DailySimulationSummary(
        reserved_vm_count=sum(template.count for template in enabled_templates),
        reservation_slot_count=sum(len(template.active_hours) * template.count for template in enabled_templates),
        active_hours=active_hours,
        reservations_by_hour=reservations_by_hour,
        peak_hour=peak_hour if enabled_templates else None,
        peak_reservation_count=peak_count,
        unplaced_by_hour={
            str(item.hour): item.summary.failed_vm_names
            for item in hourly_results
            if item.summary.failed_vm_names
        },
    )


def _cluster_peak_hours(hourly_points: list) -> list[int]:
    smoothed_scores = _smoothed_cluster_peak_scores(hourly_points)
    scored_points = [
        (hour, score)
        for hour, score in smoothed_scores.items()
        if score > 0
    ]
    if not scored_points:
        return []

    peak_score = max(score for _, score in scored_points)
    peak_hours = {
        hour
        for hour, score in scored_points
        if score >= peak_score * 0.985
    }
    for hour, score in sorted(scored_points, key=lambda item: (-item[1], item[0]))[:4]:
        if score >= peak_score * 0.9:
            peak_hours.add(hour)
    return sorted(peak_hours)


def _cluster_hourly_peak_values(hourly_points: list) -> dict[str, float | None]:
    return {
        str(hour): score
        for hour, score in _smoothed_cluster_peak_scores(hourly_points).items()
    }


def _hourly_peak_score(point) -> float:
    return max(
        point.peak_cpu_ratio or point.cpu_ratio or 0.0,
        point.peak_memory_ratio or point.memory_ratio or 0.0,
        point.peak_disk_ratio or point.disk_ratio or 0.0,
    )


def _smoothed_cluster_peak_scores(hourly_points: list) -> dict[int, float]:
    raw_scores = {
        point.hour: _hourly_peak_score(point)
        for point in hourly_points
    }
    if not raw_scores:
        return {}

    smoothed_scores: dict[int, float] = {}
    for hour in raw_scores:
        prev_1 = raw_scores.get((hour - 1) % HOURS_IN_DAY, 0.0)
        next_1 = raw_scores.get((hour + 1) % HOURS_IN_DAY, 0.0)
        prev_2 = raw_scores.get((hour - 2) % HOURS_IN_DAY, 0.0)
        next_2 = raw_scores.get((hour + 2) % HOURS_IN_DAY, 0.0)
        score = (
            raw_scores.get(hour, 0.0)
            + (prev_1 + next_1) * 0.35
            + (prev_2 + next_2) * 0.15
        )
        smoothed_scores[hour] = min(score, 1.0)
    return smoothed_scores


def _build_servers(
    server_inputs: list[ServerInput],
    cpu_overcommit_ratio: float = CPU_OVERCOMMIT_RATIO,
    disk_overcommit_ratio: float = 1.0,
) -> list[_WorkingServer]:
    """Build _WorkingServer list from inputs.

    Shared storage pools (is_shared=True) are represented as a single shared
    Python object referenced by every node that can access them.  This ensures
    that when a VM is placed on a shared pool, the capacity deduction is
    visible to ALL nodes — preventing double-counting.

    total_disk / used_disk on each server only reflect LOCAL pools so that the
    scheduler sees realistic per-node disk budgets.

    When disk_overcommit_ratio > 1.0, each pool gets overcommit_avail_gb =
    total_gb * (ratio - 1.0).  Overcommit space is only consumed after the
    pool's normal avail_gb is fully exhausted.
    """
    shared_registry: dict[str, _StorageState] = {}
    servers: list[_WorkingServer] = []
    extra_ratio = max(disk_overcommit_ratio - 1.0, 0.0)

    for inp in server_inputs:
        storage_pools: list[_StorageState] = []
        local_total = 0.0
        local_used = 0.0

        for s in inp.storages:
            if s.is_shared:
                if s.storage not in shared_registry:
                    shared_registry[s.storage] = _StorageState(
                        storage=s.storage,
                        can_vm=s.can_vm,
                        can_lxc=s.can_lxc,
                        can_iso=s.can_iso,
                        can_backup=s.can_backup,
                        is_shared=True,
                        speed_tier=s.speed_tier,
                        user_priority=s.user_priority,
                        total_gb=s.total_gb,
                        avail_gb=s.avail_gb,
                        active=s.active,
                        enabled=s.enabled,
                        overcommit_avail_gb=s.total_gb * extra_ratio,
                    )
                storage_pools.append(shared_registry[s.storage])
            else:
                pool = _StorageState(
                    storage=s.storage,
                    can_vm=s.can_vm,
                    can_lxc=s.can_lxc,
                    can_iso=s.can_iso,
                    can_backup=s.can_backup,
                    is_shared=False,
                    speed_tier=s.speed_tier,
                    user_priority=s.user_priority,
                    total_gb=s.total_gb,
                    avail_gb=s.avail_gb,
                    active=s.active,
                    enabled=s.enabled,
                    overcommit_avail_gb=s.total_gb * extra_ratio,
                )
                storage_pools.append(pool)
                local_total += s.total_gb
                local_used += s.used_gb

        # If storage list is provided, derive disk from local pools only.
        # This keeps total/used disk scoped consistently and avoids mixing
        # node-level totals with local-pool-only usage on shared-only nodes.
        if inp.storages:
            total_disk = local_total
            used_disk = local_used
        else:
            total_disk = float(inp.disk_gb)
            used_disk = float(inp.disk_used_gb)

        servers.append(
            _WorkingServer(
                name=inp.name,
                total_cpu=float(inp.cpu_cores),
                total_memory=float(inp.memory_gb),
                total_disk=total_disk,
                total_gpu=float(inp.gpu_count),
                used_cpu=float(inp.cpu_used),
                used_memory=float(inp.memory_used_gb),
                used_disk=used_disk,
                used_gpu=float(inp.gpu_used),
                current_loadavg_1=inp.current_loadavg_1,
                average_loadavg_1=inp.average_loadavg_1,
                priority=inp.priority,
                cpu_overcommit_ratio=cpu_overcommit_ratio,
                storage_pools=storage_pools,
            )
        )
    return servers


def _cpu_schedulable_capacity(total_cpu: float, ratio: float = CPU_OVERCOMMIT_RATIO) -> float:
    return max(total_cpu * ratio, 0.0)


def _memory_schedulable_capacity(total_memory: float) -> float:
    return max(total_memory * RAM_USABLE_RATIO, 0.0)


def _resolve_requested_templates(
    *,
    selected_vm_template_id: str | None,
    enabled_templates: list[VMTemplate],
) -> list[VMTemplate]:
    if selected_vm_template_id is None:
        return enabled_templates

    for template in enabled_templates:
        if template.id == selected_vm_template_id:
            return [template]
    raise ValueError(f"Selected VM template '{selected_vm_template_id}' is not enabled.")


def _expand_templates(
    *,
    templates: list[VMTemplate],
    max_instances: int,
) -> list[VMTemplate]:
    expanded: list[VMTemplate] = []
    for template in templates:
        if template.count == 1:
            expanded.append(template.model_copy(update={"count": 1}, deep=True))
            continue

        for index in range(template.count):
            expanded.append(
                template.model_copy(
                    update={
                        "id": f"{template.id}__instance_{index + 1}",
                        "count": 1,
                    },
                    deep=True,
                )
            )

    if len(expanded) > max_instances:
        raise ValueError(
            f"Requested {len(expanded)} VM instances, which exceeds max_steps={max_instances}."
        )
    return expanded


def _template_names_with_count(templates: list[VMTemplate]) -> list[str]:
    return [template.name for template in templates for _ in range(template.count)]


def _effective_template_for_hour(
    *,
    template: VMTemplate,
    hour: int,
    historical_profiles: list[HistoricalProfile],
) -> dict[str, object]:
    profile = _match_historical_profile(template, historical_profiles)
    if profile is None:
        fallback = _type_default_profile(template)
        if fallback is None:
            return {
                "requested": template,
                "template": template.model_copy(deep=True),
                "peak_template": template.model_copy(deep=True),
                "source": "requested",
                "profile_label": None,
                "cpu_ratio": None,
                "memory_ratio": None,
            }
        return _build_effective_template_result(
            template=template,
            profile_label=fallback["profile_label"],
            source="type-default",
            cpu_ratio=fallback["cpu_ratio"],
            memory_ratio=fallback["memory_ratio"],
            peak_cpu_ratio=fallback["peak_cpu_ratio"],
            peak_memory_ratio=fallback["peak_memory_ratio"],
            cpu_margin=fallback["cpu_margin"],
            ram_margin=fallback["ram_margin"],
            cpu_floor_ratio=fallback["cpu_floor_ratio"],
            ram_floor_ratio=fallback["ram_floor_ratio"],
            cpu_peak_margin=fallback["cpu_peak_margin"],
            ram_peak_margin=fallback["ram_peak_margin"],
        )

    hour_point = next((item for item in profile.hourly if item.hour == hour), None)
    cpu_ratio = _select_effective_ratio(
        hourly_ratio=hour_point.cpu_ratio if hour_point else None,
        trend_ratio=profile.trend_cpu_ratio,
        average_ratio=profile.average_cpu_ratio,
    )
    memory_ratio = _select_effective_ratio(
        hourly_ratio=hour_point.memory_ratio if hour_point else None,
        trend_ratio=profile.trend_memory_ratio,
        average_ratio=profile.average_memory_ratio,
    )
    peak_cpu_ratio = (
        hour_point.peak_cpu_ratio
        if hour_point and hour_point.peak_cpu_ratio is not None
        else profile.peak_cpu_ratio
    )
    peak_memory_ratio = (
        hour_point.peak_memory_ratio
        if hour_point and hour_point.peak_memory_ratio is not None
        else profile.peak_memory_ratio
    )
    return _build_effective_template_result(
        template=template,
        profile_label=profile.type_label,
        source="historical",
        cpu_ratio=cpu_ratio,
        memory_ratio=memory_ratio,
        peak_cpu_ratio=peak_cpu_ratio,
        peak_memory_ratio=peak_memory_ratio,
        cpu_margin=CPU_MARGIN,
        ram_margin=RAM_MARGIN,
        cpu_floor_ratio=CPU_FLOOR_RATIO,
        ram_floor_ratio=RAM_FLOOR_RATIO,
        cpu_peak_margin=CPU_PEAK_MARGIN,
        ram_peak_margin=RAM_PEAK_MARGIN,
    )


def _build_effective_template_result(
    *,
    template: VMTemplate,
    profile_label: str | None,
    source: str,
    cpu_ratio: float | None,
    memory_ratio: float | None,
    peak_cpu_ratio: float | None,
    peak_memory_ratio: float | None,
    cpu_margin: float,
    ram_margin: float,
    cpu_floor_ratio: float,
    ram_floor_ratio: float,
    cpu_peak_margin: float,
    ram_peak_margin: float,
) -> dict[str, object]:
    if peak_cpu_ratio is None:
        peak_cpu_ratio = cpu_ratio
    if peak_memory_ratio is None:
        peak_memory_ratio = memory_ratio

    effective_cpu = _effective_requested_value(
        requested=template.cpu_cores,
        ratio=cpu_ratio,
        margin=cpu_margin,
        floor_ratio=cpu_floor_ratio,
    )
    effective_memory = _effective_requested_value(
        requested=template.memory_gb,
        ratio=memory_ratio,
        margin=ram_margin,
        floor_ratio=ram_floor_ratio,
    )
    peak_cpu = min(
        template.cpu_cores,
        max(
            _scaled_requested_value(
                requested=template.cpu_cores,
                ratio=peak_cpu_ratio,
                margin=cpu_peak_margin,
            ),
            effective_cpu,
        ),
    )
    peak_memory = min(
        template.memory_gb,
        max(
            _scaled_requested_value(
                requested=template.memory_gb,
                ratio=peak_memory_ratio,
                margin=ram_peak_margin,
            ),
            effective_memory,
        ),
    )
    return {
        "requested": template,
        "template": template.model_copy(
            update={
                "cpu_cores": round(effective_cpu, 2),
                "memory_gb": round(effective_memory, 2),
            },
            deep=True,
        ),
        "peak_template": template.model_copy(
            update={
                "cpu_cores": round(peak_cpu, 2),
                "memory_gb": round(peak_memory, 2),
            },
            deep=True,
        ),
        "source": source,
        "profile_label": profile_label,
        "cpu_ratio": cpu_ratio,
        "memory_ratio": memory_ratio,
    }


def _type_default_profile(template: VMTemplate) -> dict[str, float | str] | None:
    if template.resource_type != "lxc":
        return None
    return {
        "profile_label": "LXC baseline fallback",
        "cpu_ratio": LXC_DEFAULT_CPU_RATIO,
        "memory_ratio": LXC_DEFAULT_MEMORY_RATIO,
        "peak_cpu_ratio": LXC_DEFAULT_CPU_RATIO,
        "peak_memory_ratio": LXC_DEFAULT_MEMORY_RATIO,
        "cpu_margin": LXC_CPU_MARGIN,
        "ram_margin": LXC_RAM_MARGIN,
        "cpu_floor_ratio": LXC_CPU_FLOOR_RATIO,
        "ram_floor_ratio": LXC_RAM_FLOOR_RATIO,
        "cpu_peak_margin": LXC_CPU_PEAK_MARGIN,
        "ram_peak_margin": LXC_RAM_PEAK_MARGIN,
    }


def _select_effective_ratio(
    *,
    hourly_ratio: float | None,
    trend_ratio: float | None,
    average_ratio: float | None,
) -> float | None:
    candidates = [value for value in (hourly_ratio, trend_ratio, average_ratio) if value is not None]
    if not candidates:
        return None
    return max(candidates)


def _effective_requested_value(
    *,
    requested: float,
    ratio: float | None,
    margin: float,
    floor_ratio: float,
) -> float:
    if ratio is None:
        return requested
    historical_value = requested * ratio * margin
    floor_value = requested * floor_ratio
    return min(requested, max(historical_value, floor_value))


def _scaled_requested_value(
    *,
    requested: float,
    ratio: float | None,
    margin: float,
) -> float:
    if ratio is None:
        return requested
    return requested * ratio * margin


def _match_historical_profile(
    template: VMTemplate,
    historical_profiles: list[HistoricalProfile],
) -> HistoricalProfile | None:
    template_cpu = round(template.cpu_cores, 2)
    template_memory = round(template.memory_gb, 2)
    for profile in historical_profiles:
        if profile.configured_cpu_cores is None or profile.configured_memory_gb is None:
            continue
        if profile.resource_type != template.resource_type:
            continue
        if round(profile.configured_cpu_cores, 2) == template_cpu and round(profile.configured_memory_gb, 2) == template_memory:
            return profile
    return None


def _update_calculation_row(
    *,
    calculations: list[SimulationCalculationRow],
    vm_template_id: str,
    placed_server_name: str | None,
    placement_status: str,
    placed_storage_pool: str | None = None,
    is_cpu_overcommit: bool = False,
    is_disk_overcommit: bool = False,
) -> None:
    for row in calculations:
        if row.vm_template_id == vm_template_id:
            row.placed_server_name = placed_server_name
            row.placed_storage_pool = placed_storage_pool
            row.is_cpu_overcommit = is_cpu_overcommit
            row.is_disk_overcommit = is_disk_overcommit
            row.placement_status = placement_status
            return


def _reconcile_calculations(
    *,
    calculations: list[SimulationCalculationRow],
    final_assignment_map: dict[str, str],
    final_servers: list[ServerSnapshot],
) -> None:
    for row in calculations:
        server_name = final_assignment_map.get(row.vm_template_id)
        if server_name is None:
            row.placed_server_name = None
            row.placement_status = "no_fit"
            row.peak_risk = "n/a"
            continue

        row.placed_server_name = server_name
        row.placement_status = "placed"
        row.peak_risk = _peak_risk_for_row(
            row=row,
            server=_snapshot_server_by_name(final_servers, server_name),
        )


def _peak_risk_for_row(
    *,
    row: SimulationCalculationRow,
    server: ServerSnapshot,
) -> str:
    peak_cpu_share = _share(
        server.used.cpu_cores - row.effective_cpu_cores + row.peak_cpu_cores,
        server.total.cpu_cores,
    )
    peak_memory_share = _share(
        server.used.memory_gb - row.effective_memory_gb + row.peak_memory_gb,
        _memory_schedulable_capacity(server.total.memory_gb),
    )

    if peak_cpu_share >= CPU_PEAK_HIGH_SHARE or peak_memory_share >= RAM_PEAK_HIGH_SHARE:
        return "high"
    if peak_cpu_share >= CPU_PEAK_WARN_SHARE or peak_memory_share >= RAM_PEAK_WARN_SHARE:
        return "guarded"
    return "safe"


@dataclass
class _LocalRebalanceResult:
    servers: list[_WorkingServer]
    assignment_map: dict[str, str]


def _place_template(
    *,
    servers: list[_WorkingServer],
    template: VMTemplate,
    allow_rebalance: bool,
    assignment_map: dict[str, str],
    use_node_priority: bool = False,
) -> str | None:
    choice = _choose_server(servers, template, use_node_priority=use_node_priority)
    if choice is not None:
        _apply_template(choice, template)
        assignment_map[template.id] = choice.name
        return choice.name

    if not allow_rebalance:
        return None

    rebalance_result = _local_rebalance(
        servers=servers,
        template=template,
        assignment_map=assignment_map,
        use_node_priority=use_node_priority,
    )
    if rebalance_result is None:
        return None

    servers[:] = rebalance_result.servers
    assignment_map.clear()
    assignment_map.update(rebalance_result.assignment_map)
    return assignment_map.get(template.id)


def _local_rebalance(
    *,
    servers: list[_WorkingServer],
    template: VMTemplate,
    assignment_map: dict[str, str],
    use_node_priority: bool = False,
) -> _LocalRebalanceResult | None:
    for max_moves in range(1, LOCAL_REBALANCE_MAX_MOVES + 1):
        result = _search_local_rebalance(
            servers=_clone_servers(servers),
            template=template,
            assignment_map=dict(assignment_map),
            remaining_moves=max_moves,
            moved_template_ids=set(),
            use_node_priority=use_node_priority,
        )
        if result is not None:
            return result
    return None


def _search_local_rebalance(
    *,
    servers: list[_WorkingServer],
    template: VMTemplate,
    assignment_map: dict[str, str],
    remaining_moves: int,
    moved_template_ids: set[str],
    use_node_priority: bool = False,
) -> _LocalRebalanceResult | None:
    choice = _choose_server(servers, template, use_node_priority=use_node_priority)
    if choice is not None:
        _apply_template(choice, template)
        assignment_map[template.id] = choice.name
        return _LocalRebalanceResult(servers=servers, assignment_map=assignment_map)

    if remaining_moves <= 0:
        return None

    for source in _ordered_rebalance_sources(servers):
        for placed_vm in _ordered_move_candidates(source):
            if placed_vm.template_id in moved_template_ids:
                continue
            for target in _ordered_move_targets(servers, source, placed_vm.template, use_node_priority=use_node_priority):
                next_servers = _clone_servers(servers)
                next_assignment_map = dict(assignment_map)
                next_source = _server_by_name(next_servers, source.name)
                next_target = _server_by_name(next_servers, target.name)
                moved_vm = _remove_placed_vm(next_source, placed_vm.template_id)
                if moved_vm is None:
                    continue
                if not _can_fit(next_target, moved_vm.template):
                    continue
                _apply_existing_vm(next_target, moved_vm)
                next_assignment_map[moved_vm.template_id] = next_target.name
                result = _search_local_rebalance(
                    servers=next_servers,
                    template=template,
                    assignment_map=next_assignment_map,
                    remaining_moves=remaining_moves - 1,
                    moved_template_ids=moved_template_ids | {moved_vm.template_id},
                    use_node_priority=use_node_priority,
                )
                if result is not None:
                    return result
    return None


def _snapshot_servers(servers: list[_WorkingServer]) -> list[ServerSnapshot]:
    snapshots = [_snapshot_server(server) for server in servers]
    return sorted(snapshots, key=lambda item: item.name)


def _snapshot_server(server: _WorkingServer) -> ServerSnapshot:
    vm_counts = Counter(item.template.name for item in server.placed_vms)
    cpu_remaining = max(_cpu_schedulable_capacity(server.total_cpu, server.cpu_overcommit_ratio) - server.used_cpu, 0.0)
    memory_remaining = max(
        _memory_schedulable_capacity(server.total_memory) - server.used_memory,
        0.0,
    )
    return ServerSnapshot(
        name=server.name,
        total=ResourceUsage(
            cpu_cores=round(server.total_cpu, 2),
            memory_gb=round(server.total_memory, 2),
            disk_gb=round(server.total_disk, 2),
            gpu_count=round(server.total_gpu, 2),
        ),
        used=ResourceUsage(
            cpu_cores=round(server.used_cpu, 2),
            memory_gb=round(server.used_memory, 2),
            disk_gb=round(server.used_disk, 2),
            gpu_count=round(server.used_gpu, 2),
        ),
        remaining=ResourceUsage(
            cpu_cores=round(cpu_remaining, 2),
            memory_gb=round(memory_remaining, 2),
            disk_gb=round(max(server.total_disk - server.used_disk, 0.0), 2),
            gpu_count=round(max(server.total_gpu - server.used_gpu, 0.0), 2),
        ),
        shares=_server_shares(server),
        dominant_share=round(_dominant_share(server), 4),
        average_share=round(_average_share(server), 4),
        placement_count=server.placement_count,
        current_loadavg_1=server.current_loadavg_1,
        average_loadavg_1=server.average_loadavg_1,
        priority=server.priority,
        storages=[
            StorageInfo(
                storage=pool.storage,
                type=None,
                total_gb=round(pool.total_gb, 2),
                used_gb=round(pool.total_gb - pool.avail_gb, 2),
                avail_gb=round(pool.avail_gb, 2),
                used_fraction=round(
                    (pool.total_gb - pool.avail_gb) / pool.total_gb
                    if pool.total_gb > EPSILON else 0.0,
                    4,
                ),
                can_vm=pool.can_vm,
                can_lxc=pool.can_lxc,
                can_iso=pool.can_iso,
                can_backup=pool.can_backup,
                is_shared=pool.is_shared,
                active=pool.active,
                enabled=pool.enabled,
                speed_tier=pool.speed_tier,
                user_priority=pool.user_priority,
            )
            for pool in server.storage_pools
        ],
        placed_vms=[item.template.name for item in server.placed_vms],
        vm_stack=[
            VmStackItem(name=name, count=count)
            for name, count in sorted(vm_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )


def _server_shares(server: _WorkingServer) -> ResourceShares:
    return ResourceShares(
        cpu=round(_share(server.used_cpu, _cpu_schedulable_capacity(server.total_cpu, server.cpu_overcommit_ratio)), 4),
        memory=round(
            _share(server.used_memory, _memory_schedulable_capacity(server.total_memory)),
            4,
        ),
        disk=round(_share(server.used_disk, server.total_disk), 4),
        gpu=round(_share(server.used_gpu, server.total_gpu), 4),
    )


def _share(used: float, total: float) -> float:
    if total <= EPSILON:
        return 0.0
    return max(used / total, 0.0)


def _dominant_share(server: _WorkingServer) -> float:
    shares = _weighted_share_values(server)
    return max(shares) if shares else 0.0


def _average_share(server: _WorkingServer) -> float:
    shares = _weighted_share_values(server)
    return mean(shares) if shares else 0.0


def _weighted_share_values(server: _WorkingServer) -> list[float]:
    values = [
        _weighted_share(
            _share(server.used_cpu, _cpu_schedulable_capacity(server.total_cpu, server.cpu_overcommit_ratio)),
            CPU_SHARE_WEIGHT,
        ),
        _weighted_share(
            _share(server.used_memory, _memory_schedulable_capacity(server.total_memory)),
            MEMORY_SHARE_WEIGHT,
        ),
        _weighted_share(_share(server.used_disk, server.total_disk), DISK_SHARE_WEIGHT),
    ]
    if server.total_gpu > EPSILON:
        values.append(
            _weighted_share(_share(server.used_gpu, server.total_gpu), GPU_SHARE_WEIGHT)
        )
    return values


def _weighted_share(share: float, weight: float) -> float:
    return share * weight


def _storage_scope_score(pool: _StorageState, preference: str) -> int:
    """0 = preferred scope, 1 = fallback — never a hard exclusion."""
    if preference == "local":
        return 0 if not pool.is_shared else 1
    if preference == "shared":
        return 0 if pool.is_shared else 1
    return 0  # "any"


def _best_storage_for_template(
    server: _WorkingServer,
    template: VMTemplate,
) -> _StorageState | None:
    """Return the best storage pool for the template using combined scoring.

    Two-phase selection:
      Phase 1 — Normal (no overcommit): pools where avail_gb >= disk_gb.
        Sort key (lower = better):
          1. Exact preferred_storage_name match (instant win)
          2. Scope mismatch penalty (0 = matches preference, 1 = fallback)
          3. Speed tier rank: nvme=0, ssd=1, hdd=2, unknown=3
          4. User priority (1 = most preferred)
          5. Most available space (negated for ascending sort)
      Phase 2 — Overcommit: only when no normal pool can fit.
        Pools where avail_gb + overcommit_avail_gb >= disk_gb.
        Additional leading sort key: overcommit_placed_count ascending
        (ensures overcommit load is spread across pools evenly).
    """
    is_lxc = template.resource_type == "lxc"
    preference = template.storage_scope_preference
    preferred_name = template.preferred_storage_name

    capable = [
        pool for pool in server.storage_pools
        if pool.active
        and pool.enabled
        and (pool.can_lxc if is_lxc else pool.can_vm)
    ]

    # Phase 1: normal candidates (no overcommit needed)
    normal = [p for p in capable if p.avail_gb + EPSILON >= template.disk_gb]
    if normal:
        if preferred_name:
            for p in normal:
                if p.storage == preferred_name:
                    return p
        return min(
            normal,
            key=lambda p: (
                _storage_scope_score(p, preference),
                _SPEED_RANK.get(p.speed_tier, 3),
                p.user_priority,
                p.placed_count,   # within same tier/priority: spread evenly by count
                -p.avail_gb,
            ),
        )

    # Phase 2: overcommit candidates (spread evenly across pools)
    overcommit = [
        p for p in capable
        if p.avail_gb + p.overcommit_avail_gb + EPSILON >= template.disk_gb
    ]
    if not overcommit:
        return None
    if preferred_name:
        for p in overcommit:
            if p.storage == preferred_name:
                return p
    return min(
        overcommit,
        key=lambda p: (
            p.overcommit_placed_count,          # spread: fewest overcommit placements first
            _storage_scope_score(p, preference),
            _SPEED_RANK.get(p.speed_tier, 3),
            p.user_priority,
            -(p.avail_gb + p.overcommit_avail_gb),
        ),
    )


def _can_fit_cpu_normal(server: _WorkingServer, template: VMTemplate) -> bool:
    """True if the VM fits within physical (non-overcommit) CPU headroom."""
    return (server.total_cpu - server.used_cpu) + EPSILON >= template.cpu_cores


def _can_fit(server: _WorkingServer, template: VMTemplate) -> bool:
    """Full fit check including CPU overcommit capacity."""
    if (_cpu_schedulable_capacity(server.total_cpu, server.cpu_overcommit_ratio) - server.used_cpu) + EPSILON < template.cpu_cores:
        return False
    if (_memory_schedulable_capacity(server.total_memory) - server.used_memory) + EPSILON < template.memory_gb:
        return False
    # Disk: use per-storage-pool check when available (includes overcommit); fall back to aggregate.
    if server.storage_pools:
        if _best_storage_for_template(server, template) is None:
            return False
    elif (server.total_disk - server.used_disk) + EPSILON < template.disk_gb:
        return False
    if (server.total_gpu - server.used_gpu) + EPSILON < template.gpu_count:
        return False
    return True


def _choose_server(
    servers: list[_WorkingServer],
    template: VMTemplate,
    *,
    use_node_priority: bool = False,
) -> _WorkingServer | None:
    # Phase 1: candidates with physical CPU headroom (no CPU overcommit needed).
    normal_cpu = [s for s in servers if _can_fit_cpu_normal(s, template) and _can_fit(s, template)]
    if normal_cpu:
        return min(
            normal_cpu,
            key=lambda s: _placement_sort_key(s, template, migration_cost=0.0, use_node_priority=use_node_priority),
        )
    # Phase 2: allow CPU overcommit — only when no normal candidate exists.
    overcommit_cpu = [s for s in servers if _can_fit(s, template)]
    if not overcommit_cpu:
        return None
    return min(
        overcommit_cpu,
        key=lambda s: _placement_sort_key(s, template, migration_cost=0.0, use_node_priority=use_node_priority),
    )


def _projected_dominant_share(server: _WorkingServer, template: VMTemplate) -> float:
    return max(_projected_share_values(server, template))


def _projected_average_share(server: _WorkingServer, template: VMTemplate) -> float:
    return mean(_projected_share_values(server, template))


def _projected_share_values(server: _WorkingServer, template: VMTemplate) -> list[float]:
    values = [
        _weighted_share(
            _share(
                server.used_cpu + template.cpu_cores,
                _cpu_schedulable_capacity(server.total_cpu, server.cpu_overcommit_ratio),
            ),
            CPU_SHARE_WEIGHT,
        ),
        _weighted_share(
            _share(
                server.used_memory + template.memory_gb,
                _memory_schedulable_capacity(server.total_memory),
            ),
            MEMORY_SHARE_WEIGHT,
        ),
        _weighted_share(
            _share(server.used_disk + template.disk_gb, server.total_disk),
            DISK_SHARE_WEIGHT,
        ),
    ]
    if server.total_gpu > EPSILON:
        values.append(
            _weighted_share(
                _share(server.used_gpu + template.gpu_count, server.total_gpu),
                GPU_SHARE_WEIGHT,
            )
        )
    return values


def _placement_sort_key(
    server: _WorkingServer,
    template: VMTemplate,
    *,
    migration_cost: float,
    use_node_priority: bool = False,
) -> tuple:
    projected_dominant_share = _projected_dominant_share(server, template)
    projected_average_share = _projected_average_share(server, template)
    projected_cpu_share = _projected_physical_cpu_share(server, template)
    penalty = _resource_penalty(server, template)
    score = projected_dominant_share + penalty + migration_cost
    if use_node_priority:
        # Primary: node priority (1 = most preferred).
        # Secondary: placement_count — within the same priority tier, spread VMs evenly across nodes.
        # Tertiary: dominant share score — among equally-loaded nodes, prefer lower load.
        return (
            server.priority,
            server.placement_count,
            score,
            projected_average_share,
            projected_cpu_share,
            server.name,
        )
    # Standard mode: placement_count first for even spreading across all nodes,
    # then dominant share score for load balance among equally-placed nodes.
    # _can_fit() already prevents overloading, so round-robin is safe.
    return (
        server.placement_count,
        score,
        projected_average_share,
        projected_cpu_share,
        server.name,
    )


def _resource_penalty(server: _WorkingServer, template: VMTemplate) -> float:
    projected_cpu_share = _projected_physical_cpu_share(server, template)
    projected_memory_share = _projected_memory_policy_share(server, template)
    projected_disk_share = _projected_disk_share(server, template)
    cpu_penalty = _cpu_contention_penalty(projected_cpu_share)
    memory_penalty = 1.0 if projected_memory_share > 1.0 + EPSILON else 0.0
    disk_penalty = _disk_latency_penalty(projected_disk_share)
    loadavg_penalty = _loadavg_penalty(_server_loadavg_per_core(server))
    return (
        (cpu_penalty * CPU_CONTENTION_WEIGHT)
        + (memory_penalty * MEMORY_OVERFLOW_WEIGHT)
        + (disk_penalty * DISK_CONTENTION_WEIGHT)
        + (loadavg_penalty * LOADAVG_PENALTY_WEIGHT)
    )


def _cpu_contention_penalty(share: float) -> float:
    if share <= CPU_SAFE_SHARE:
        return 0.0
    if share >= CPU_MAX_SHARE:
        return 1.0
    return (share - CPU_SAFE_SHARE) / (CPU_MAX_SHARE - CPU_SAFE_SHARE)


def _disk_latency_penalty(share: float) -> float:
    if share <= DISK_SAFE_SHARE:
        return 0.0
    if share >= DISK_MAX_SHARE:
        return 1.0
    return (share - DISK_SAFE_SHARE) / (DISK_MAX_SHARE - DISK_SAFE_SHARE)


def _loadavg_penalty(loadavg_per_core: float | None) -> float:
    if loadavg_per_core is None or loadavg_per_core <= LOADAVG_WARN_PER_CORE:
        return 0.0
    if loadavg_per_core >= LOADAVG_MAX_PER_CORE:
        return 1.0
    return (loadavg_per_core - LOADAVG_WARN_PER_CORE) / (LOADAVG_MAX_PER_CORE - LOADAVG_WARN_PER_CORE)


def _server_reference_loadavg_1(server: _WorkingServer | ServerSnapshot) -> float | None:
    candidates = [
        value
        for value in (
            getattr(server, "current_loadavg_1", None),
            getattr(server, "average_loadavg_1", None),
        )
        if value is not None
    ]
    if not candidates:
        return None
    return max(candidates)


def _server_loadavg_per_core(server: _WorkingServer | ServerSnapshot) -> float | None:
    total_cpu = getattr(server, "total_cpu", None)
    if total_cpu is None:
        total = getattr(server, "total", None)
        total_cpu = getattr(total, "cpu_cores", None)
    if total_cpu is None or total_cpu <= EPSILON:
        return None
    loadavg_1 = _server_reference_loadavg_1(server)
    if loadavg_1 is None:
        return None
    return loadavg_1 / total_cpu


def _projected_physical_cpu_share(server: _WorkingServer, template: VMTemplate) -> float:
    return _share(server.used_cpu + template.cpu_cores, server.total_cpu)


def _projected_memory_policy_share(server: _WorkingServer, template: VMTemplate) -> float:
    return _share(
        server.used_memory + template.memory_gb,
        _memory_schedulable_capacity(server.total_memory),
    )


def _projected_disk_share(server: _WorkingServer, template: VMTemplate) -> float:
    return _share(server.used_disk + template.disk_gb, server.total_disk)


def _clone_servers(servers: list[_WorkingServer]) -> list[_WorkingServer]:
    """Deep-clone the server cluster for rebalance search.

    Shared pools (is_shared=True) are deduplicated by ``pool.storage``
    so that pools with the same storage name referenced by multiple
    servers become one cloned object shared by those cloned servers.
    """
    shared_pool_map: dict[str, _StorageState] = {}
    cloned: list[_WorkingServer] = []

    for server in servers:
        new_pools: list[_StorageState] = []
        for pool in server.storage_pools:
            if pool.is_shared:
                pool_key = pool.storage
                if pool_key not in shared_pool_map:
                    shared_pool_map[pool_key] = _StorageState(
                        storage=pool.storage,
                        can_vm=pool.can_vm,
                        can_lxc=pool.can_lxc,
                        can_iso=pool.can_iso,
                        can_backup=pool.can_backup,
                        is_shared=True,
                        speed_tier=pool.speed_tier,
                        user_priority=pool.user_priority,
                        total_gb=pool.total_gb,
                        avail_gb=pool.avail_gb,
                        active=pool.active,
                        enabled=pool.enabled,
                        placed_count=pool.placed_count,
                        overcommit_avail_gb=pool.overcommit_avail_gb,
                        overcommit_placed_count=pool.overcommit_placed_count,
                    )
                new_pools.append(shared_pool_map[pool_key])
            else:
                new_pools.append(
                    _StorageState(
                        storage=pool.storage,
                        can_vm=pool.can_vm,
                        can_lxc=pool.can_lxc,
                        can_iso=pool.can_iso,
                        can_backup=pool.can_backup,
                        is_shared=False,
                        speed_tier=pool.speed_tier,
                        user_priority=pool.user_priority,
                        total_gb=pool.total_gb,
                        avail_gb=pool.avail_gb,
                        active=pool.active,
                        enabled=pool.enabled,
                        placed_count=pool.placed_count,
                        overcommit_avail_gb=pool.overcommit_avail_gb,
                        overcommit_placed_count=pool.overcommit_placed_count,
                    )
                )
        cloned.append(
            _WorkingServer(
                name=server.name,
                total_cpu=server.total_cpu,
                total_memory=server.total_memory,
                total_disk=server.total_disk,
                total_gpu=server.total_gpu,
                used_cpu=server.used_cpu,
                used_memory=server.used_memory,
                used_disk=server.used_disk,
                used_gpu=server.used_gpu,
                current_loadavg_1=server.current_loadavg_1,
                average_loadavg_1=server.average_loadavg_1,
                priority=server.priority,
                cpu_overcommit_ratio=server.cpu_overcommit_ratio,
                storage_pools=new_pools,
                placed_vms=[
                    _PlacedVm(
                        template_id=item.template_id,
                        template=item.template.model_copy(deep=True),
                        storage_pool=item.storage_pool,
                        is_cpu_overcommit=item.is_cpu_overcommit,
                        is_overcommit=item.is_overcommit,
                        overcommit_disk_gb=item.overcommit_disk_gb,
                    )
                    for item in server.placed_vms
                ],
            )
        )
    return cloned


def _server_by_name(servers: list[_WorkingServer], server_name: str) -> _WorkingServer:
    for server in servers:
        if server.name == server_name:
            return server
    raise ValueError(f"Server '{server_name}' was not found.")


def _ordered_rebalance_sources(servers: list[_WorkingServer]) -> list[_WorkingServer]:
    return sorted(
        [server for server in servers if server.placed_vms],
        key=lambda server: (
            -_dominant_share(server),
            -_share(server.used_memory, _memory_schedulable_capacity(server.total_memory)),
            -_share(server.used_cpu, server.total_cpu),
            server.name,
        ),
    )


def _ordered_move_candidates(server: _WorkingServer) -> list[_PlacedVm]:
    return sorted(
        server.placed_vms,
        key=lambda item: (
            _template_resource_value(item.template, "gpu"),
            _template_resource_value(item.template, "disk"),
            _template_resource_value(item.template, "memory"),
            _template_resource_value(item.template, "cpu"),
        ),
        reverse=True,
    )


def _ordered_move_targets(
    servers: list[_WorkingServer],
    source_server: _WorkingServer,
    template: VMTemplate,
    *,
    use_node_priority: bool = False,
) -> list[_WorkingServer]:
    candidates = [
        server
        for server in servers
        if server.name != source_server.name and _can_fit(server, template)
    ]
    return sorted(
        candidates,
        key=lambda server: _placement_sort_key(
            server,
            template,
            migration_cost=MIGRATION_COST,
            use_node_priority=use_node_priority,
        ),
    )


def _remove_placed_vm(server: _WorkingServer, template_id: str) -> _PlacedVm | None:
    for index, placed_vm in enumerate(server.placed_vms):
        if placed_vm.template_id != template_id:
            continue
        server.placed_vms.pop(index)
        server.used_cpu -= placed_vm.template.cpu_cores
        server.used_memory -= placed_vm.template.memory_gb
        server.used_gpu -= placed_vm.template.gpu_count
        if placed_vm.storage_pool:
            for pool in server.storage_pools:
                if pool.storage == placed_vm.storage_pool:
                    if placed_vm.is_overcommit:
                        # Restore: put overcommit portion back to overcommit bucket, normal portion to avail_gb.
                        from_normal = placed_vm.template.disk_gb - placed_vm.overcommit_disk_gb
                        pool.avail_gb += from_normal
                        pool.overcommit_avail_gb += placed_vm.overcommit_disk_gb
                        pool.overcommit_placed_count = max(pool.overcommit_placed_count - 1, 0)
                    else:
                        pool.avail_gb += placed_vm.template.disk_gb
                        pool.placed_count = max(pool.placed_count - 1, 0)
                    if not pool.is_shared:
                        server.used_disk -= placed_vm.template.disk_gb
                    break
        else:
            server.used_disk -= placed_vm.template.disk_gb
        return placed_vm
    return None


def _apply_existing_vm(server: _WorkingServer, placed_vm: _PlacedVm) -> None:
    server.used_cpu += placed_vm.template.cpu_cores
    server.used_memory += placed_vm.template.memory_gb
    server.used_gpu += placed_vm.template.gpu_count
    if placed_vm.storage_pool:
        for pool in server.storage_pools:
            if pool.storage == placed_vm.storage_pool:
                if placed_vm.is_overcommit:
                    from_normal = placed_vm.template.disk_gb - placed_vm.overcommit_disk_gb
                    pool.avail_gb -= from_normal
                    pool.overcommit_avail_gb -= placed_vm.overcommit_disk_gb
                    pool.overcommit_placed_count += 1
                else:
                    pool.avail_gb -= placed_vm.template.disk_gb
                    pool.placed_count += 1
                if not pool.is_shared:
                    server.used_disk += placed_vm.template.disk_gb
                break
    else:
        server.used_disk += placed_vm.template.disk_gb
    server.placed_vms.append(placed_vm)


def _apply_template(server: _WorkingServer, template: VMTemplate) -> None:
    # Detect CPU overcommit BEFORE updating used_cpu.
    is_cpu_overcommit = (server.used_cpu + template.cpu_cores) > server.total_cpu + EPSILON
    server.used_cpu += template.cpu_cores
    server.used_memory += template.memory_gb
    server.used_gpu += template.gpu_count
    pool = _best_storage_for_template(server, template) if server.storage_pools else None
    is_overcommit = False
    overcommit_disk_gb = 0.0
    if pool is not None:
        if pool.avail_gb + EPSILON < template.disk_gb:
            # Overcommit placement: drain all remaining normal space first, then overcommit bucket.
            is_overcommit = True
            from_normal = max(pool.avail_gb, 0.0)
            overcommit_disk_gb = template.disk_gb - from_normal
            pool.avail_gb = 0.0
            pool.overcommit_avail_gb -= overcommit_disk_gb
            pool.overcommit_avail_gb = max(pool.overcommit_avail_gb, 0.0)
            pool.overcommit_placed_count += 1
        else:
            pool.avail_gb -= template.disk_gb
            pool.avail_gb = max(pool.avail_gb, 0.0)
            pool.placed_count += 1
        if not pool.is_shared:
            server.used_disk += template.disk_gb
    else:
        server.used_disk += template.disk_gb
    server.placed_vms.append(
        _PlacedVm(
            template_id=template.id,
            template=template.model_copy(deep=True),
            storage_pool=pool.storage if pool else None,
            is_cpu_overcommit=is_cpu_overcommit,
            is_overcommit=is_overcommit,
            overcommit_disk_gb=overcommit_disk_gb,
        )
    )


def _build_reason(server: _WorkingServer, template: VMTemplate) -> str:
    shares = _server_shares(server)
    return (
        f"Placed on {server.name} because its projected weighted share and contention score are lowest. "
        f"After placement: CPU {shares.cpu:.0%}, RAM {shares.memory:.0%}, "
        f"Disk {shares.disk:.0%}, GPU {shares.gpu:.0%}."
    )


def _build_rebalance_reason(
    *,
    template: VMTemplate,
    server_name: str,
    server: _WorkingServer,
    previous_assignments: dict[str, str],
    current_assignments: dict[str, str],
) -> str:
    moved = [
        template_id
        for template_id, previous_server in previous_assignments.items()
        if current_assignments.get(template_id) != previous_server
    ]
    load_text = _server_load_warning_text(server)
    if moved:
        return (
            f"Placed {template.name} on {server_name}. "
            f"Auto-rebalanced {len(moved)} existing VM(s) across the cluster to free space."
            f"{load_text}"
        )
    return (
        f"Placed {template.name} on {server_name} using the current cluster balance."
        f"{load_text}"
    )


def _server_load_warning_text(server: _WorkingServer | ServerSnapshot) -> str:
    loadavg_1 = _server_reference_loadavg_1(server)
    loadavg_per_core = _server_loadavg_per_core(server)
    if loadavg_1 is None or loadavg_per_core is None or loadavg_per_core < LOADAVG_WARN_PER_CORE:
        return ""
    return (
        f" Host loadavg is elevated at {loadavg_1:.2f} "
        f"({loadavg_per_core:.2f} per core), so a soft penalty was applied instead of blocking placement."
    )


def _build_summary(
    *,
    final_servers: list[ServerSnapshot],
    placements: list[PlacementRecord],
    stop_reason: str,
    enabled_templates: list[VMTemplate],
    requested_templates: list[VMTemplate],
    failed_templates: list[VMTemplate],
) -> SimulationSummary:
    placed_by_vm: dict[str, int] = {}
    placed_by_server: dict[str, int] = {}
    for placement in placements:
        placed_by_vm[placement.vm_name] = placed_by_vm.get(placement.vm_name, 0) + 1
        placed_by_server[placement.server_name] = (
            placed_by_server.get(placement.server_name, 0) + 1
        )

    # NOTE: Uses default CPU_OVERCOMMIT_RATIO for cluster-level share summary.
    # Per-server ratio from SimulationRequest is used during placement but not
    # propagated to ServerSnapshot, so cluster shares are approximate.
    cluster_cpu_policy_total = sum(
        _cpu_schedulable_capacity(server.total.cpu_cores) for server in final_servers
    )
    cluster_memory_policy_total = sum(
        _memory_schedulable_capacity(server.total.memory_gb) for server in final_servers
    )
    cluster_disk_total = sum(server.total.disk_gb for server in final_servers)
    cluster_gpu_total = sum(server.total.gpu_count for server in final_servers)

    cluster_cpu_used = sum(server.used.cpu_cores for server in final_servers)
    cluster_memory_used = sum(server.used.memory_gb for server in final_servers)
    cluster_disk_used = sum(server.used.disk_gb for server in final_servers)
    cluster_gpu_used = sum(server.used.gpu_count for server in final_servers)

    cluster_shares = ResourceShares(
        cpu=round(_share(cluster_cpu_used, cluster_cpu_policy_total), 4),
        memory=round(_share(cluster_memory_used, cluster_memory_policy_total), 4),
        disk=round(_share(cluster_disk_used, cluster_disk_total), 4),
        gpu=round(_share(cluster_gpu_used, cluster_gpu_total), 4),
    )
    highest_dominant = max(
        (server.dominant_share for server in final_servers),
        default=0.0,
    )
    most_loaded = max(
        final_servers,
        key=lambda server: server.dominant_share,
        default=None,
    )
    bottleneck_resource = _find_bottleneck_resource(most_loaded) if most_loaded else None
    relief_actions = _build_relief_actions(
        final_servers=final_servers,
        enabled_templates=enabled_templates,
        failed_templates=failed_templates,
        bottleneck_server=most_loaded,
        bottleneck_resource=bottleneck_resource,
        stop_reason=stop_reason,
    )
    single_template = requested_templates[0] if len(requested_templates) == 1 else None
    if not requested_templates:
        narrative = "Three empty PVE nodes are ready. Add one or more VMs to start the simulation."
    else:
        narrative = (
            f"Placed {len(placements)} of {len(requested_templates)} requested VMs. "
            f"Cluster policy utilization is CPU {cluster_shares.cpu:.0%}, RAM {cluster_shares.memory:.0%}, "
            f"Disk {cluster_shares.disk:.0%}. "
            + (
                f"The tightest node is {most_loaded.name} at dominant share "
                f"{most_loaded.dominant_share:.0%}."
                if most_loaded is not None
                else "No node state is available."
            )
        )
        load_warnings = [
            f"{server.name} ({_server_reference_loadavg_1(server):.2f}, {_server_loadavg_per_core(server):.2f} per core)"
            for server in final_servers
            if _server_reference_loadavg_1(server) is not None
            and _server_loadavg_per_core(server) is not None
            and _server_loadavg_per_core(server) >= LOADAVG_WARN_PER_CORE
        ]
        if load_warnings:
            narrative += " Loadavg penalty is active for: " + ", ".join(load_warnings) + "."
    return SimulationSummary(
        selected_vm_name=single_template.name if single_template else None,
        requested_vm_count=len(requested_templates),
        total_placements=len(placements),
        placed_by_vm=placed_by_vm,
        placed_by_server=placed_by_server,
        failed_vm_names=[template.name for template in failed_templates],
        cluster_shares=cluster_shares,
        highest_server_dominant_share=round(highest_dominant, 4),
        recommendation_possible=bool(placements) if single_template else False,
        recommendation_target=placements[0].server_name if single_template and placements else None,
        recommendation_reason=placements[0].reason if single_template and placements else None,
        bottleneck_server=most_loaded.name if most_loaded else None,
        bottleneck_resource=bottleneck_resource,
        stop_reason=stop_reason,
        narrative=narrative,
        relief_actions=relief_actions,
    )


def _snapshot_server_by_name(
    snapshots: list[ServerSnapshot],
    server_name: str,
) -> ServerSnapshot:
    for snapshot in snapshots:
        if snapshot.name == server_name:
            return snapshot
    raise ValueError(f"Snapshot for server '{server_name}' was not found.")


def _snapshot_server_shares(
    snapshots: list[ServerSnapshot],
    server_name: str,
) -> ResourceShares:
    return _snapshot_server_by_name(snapshots, server_name).shares


def _snapshot_dominant_share(
    snapshots: list[ServerSnapshot],
    server_name: str,
) -> float:
    return _snapshot_server_by_name(snapshots, server_name).dominant_share


def _snapshot_average_share(
    snapshots: list[ServerSnapshot],
    server_name: str,
) -> float:
    return _snapshot_server_by_name(snapshots, server_name).average_share


def _find_bottleneck_resource(server: ServerSnapshot | None) -> str | None:
    if server is None:
        return None
    shares = {
        "cpu": server.shares.cpu * CPU_SHARE_WEIGHT,
        "memory": server.shares.memory * MEMORY_SHARE_WEIGHT,
        "disk": server.shares.disk * DISK_SHARE_WEIGHT,
        "gpu": server.shares.gpu * GPU_SHARE_WEIGHT,
    }
    return max(shares.items(), key=lambda item: item[1])[0]


def _build_relief_actions(
    *,
    final_servers: list[ServerSnapshot],
    enabled_templates: list[VMTemplate],
    failed_templates: list[VMTemplate],
    bottleneck_server: ServerSnapshot | None,
    bottleneck_resource: str | None,
    stop_reason: str,
) -> list[ReliefSuggestion]:
    if bottleneck_server is None or bottleneck_resource is None:
        return []

    if not failed_templates:
        return []

    template_by_name = {template.name: template for template in enabled_templates}
    actions: list[ReliefSuggestion] = []
    heaviest_vm = _pick_vm_to_move(
        bottleneck_server=bottleneck_server,
        bottleneck_resource=bottleneck_resource,
        template_by_name=template_by_name,
    )
    if heaviest_vm is not None:
        receiver = _pick_receiver(
            final_servers=final_servers,
            source_server=bottleneck_server,
            template=heaviest_vm,
        )
        release_text = _template_release_text(heaviest_vm)
        if receiver is not None:
            actions.append(
                ReliefSuggestion(
                    title=f"先搬移 1 台 {heaviest_vm.name}",
                    detail=(
                        f"目前最緊的是 {bottleneck_server.name} 的 "
                        f"{_resource_label(bottleneck_resource)}。優先把 1 台 "
                        f"{heaviest_vm.name} 挪到 {receiver.name}，可釋放 {release_text}。"
                    ),
                )
            )
        else:
            actions.append(
                ReliefSuggestion(
                    title=f"先在 {bottleneck_server.name} 釋放容量",
                    detail=(
                        f"{bottleneck_server.name} 的 "
                        f"{_resource_label(bottleneck_resource)} 已成瓶頸。"
                        f"若沒有其他節點可承接，先停止、縮規或搬走 1 台 "
                        f"{heaviest_vm.name}，可釋放 {release_text}。"
                    ),
                )
            )

    blocked_template = _pick_blocked_template(final_servers, failed_templates)
    if blocked_template is not None:
        actions.append(
            ReliefSuggestion(
                title=f"若要再放 1 台 {blocked_template.name}",
                detail=(
                    "至少要先空出 "
                    f"{_template_release_text(blocked_template)}。"
                ),
            )
        )

    healthiest_server = min(
        final_servers,
        key=lambda server: (server.dominant_share, server.name),
        default=None,
    )
    if healthiest_server is not None and healthiest_server.name != bottleneck_server.name:
        actions.append(
            ReliefSuggestion(
                title=f"優先把 workload 往 {healthiest_server.name} 集中",
                detail=(
                    f"{healthiest_server.name} 目前 dominant share 最低，"
                    "如果要做人工作業遷移，先檢查它是否能接收較大的 VM。"
                ),
            )
        )
    return actions[:3]


def _pick_vm_to_move(
    *,
    bottleneck_server: ServerSnapshot,
    bottleneck_resource: str,
    template_by_name: dict[str, VMTemplate],
) -> VMTemplate | None:
    candidates = [
        template_by_name[item.name]
        for item in bottleneck_server.vm_stack
        if item.name in template_by_name
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda template: (
            _template_resource_value(template, bottleneck_resource),
            template.cpu_cores,
            template.memory_gb,
            template.disk_gb,
            template.gpu_count,
        ),
    )


def _pick_receiver(
    *,
    final_servers: list[ServerSnapshot],
    source_server: ServerSnapshot,
    template: VMTemplate,
) -> ServerSnapshot | None:
    candidates = [
        server
        for server in final_servers
        if server.name != source_server.name and _server_can_fit_snapshot(server, template)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda server: (server.dominant_share, server.name))


def _pick_blocked_template(
    final_servers: list[ServerSnapshot],
    enabled_templates: list[VMTemplate],
) -> VMTemplate | None:
    blocked = [
        template
        for template in enabled_templates
        if not any(_server_can_fit_snapshot(server, template) for server in final_servers)
    ]
    if not blocked:
        return None
    return max(
        blocked,
        key=lambda template: (
            template.gpu_count,
            template.cpu_cores,
            template.memory_gb,
            template.disk_gb,
        ),
    )


def _server_can_fit_snapshot(server: ServerSnapshot, template: VMTemplate) -> bool:
    if server.remaining.cpu_cores + EPSILON < template.cpu_cores:
        return False
    if server.remaining.memory_gb + EPSILON < template.memory_gb:
        return False
    if server.remaining.disk_gb + EPSILON < template.disk_gb:
        return False
    if server.remaining.gpu_count + EPSILON < template.gpu_count:
        return False
    return True


def _template_release_text(template: VMTemplate) -> str:
    gpu_text = f"、GPU {template.gpu_count:g}" if template.gpu_count > 0 else ""
    return (
        f"CPU {template.cpu_cores:g}、RAM {template.memory_gb:g} GiB、"
        f"Disk {template.disk_gb:g} GiB{gpu_text}"
    )


def _template_sort_key(template: VMTemplate) -> tuple[float, float, float, float]:
    return (
        template.gpu_count,
        template.cpu_cores,
        template.memory_gb,
        template.disk_gb,
    )


def _template_resource_value(template: VMTemplate, resource: str) -> float:
    mapping = {
        "cpu": template.cpu_cores,
        "memory": template.memory_gb,
        "disk": template.disk_gb,
        "gpu": template.gpu_count,
    }
    return float(mapping[resource])


def _resource_label(resource: str) -> str:
    return {
        "cpu": "CPU",
        "memory": "RAM",
        "disk": "Disk",
        "gpu": "GPU",
    }[resource]


def _hour_label(hour: int) -> str:
    next_hour = (hour + 1) % HOURS_IN_DAY
    return f"{hour:02d}:00-{next_hour:02d}:00"
