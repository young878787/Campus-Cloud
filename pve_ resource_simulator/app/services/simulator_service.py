from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import mean

from app.schemas import (
    DailySimulationSummary,
    DefaultScenarioResponse,
    HOURS_IN_DAY,
    HourlySimulation,
    PlacementRecord,
    ReliefSuggestion,
    ResourceShares,
    ResourceUsage,
    ServerInput,
    ServerSnapshot,
    SimulationRequest,
    SimulationResponse,
    SimulationState,
    SimulationSummary,
    VMTemplate,
    VmStackItem,
)


EPSILON = 1e-9


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
    placed_vms: list[str] = field(default_factory=list)

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
            ),
        ],
        vm_templates=[],
        note=(
            "Default scenario starts with three empty PVE nodes and no VMs. "
            "Add VM reservations, mark their hourly windows, and review placement "
            "hour by hour across the day."
        ),
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
    servers = [_to_working_server(item) for item in request.servers]
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

    if not requested_templates:
        final_servers = _snapshot_servers(servers)
        summary = _build_summary(
            final_servers=final_servers,
            placements=[],
            stop_reason=f"No reservations in {_hour_label(hour)}.",
            enabled_templates=requested_templates,
            requested_templates=requested_templates,
            failed_templates=[],
        )
        return HourlySimulation(
            hour=hour,
            label=_hour_label(hour),
            active_vm_names=[],
            reserved_vm_names=[template.name for template in enabled_templates],
            placements=[],
            states=states,
            summary=summary,
        )

    previous_assignments: dict[str, str] = {}
    final_servers = _snapshot_servers(servers)
    for index, template in enumerate(requested_templates, start=1):
        current_templates = requested_templates[:index]
        allocation = _rebalance_allocation(
            base_servers=request.servers,
            templates=current_templates,
            allow_rebalance=request.allow_rebalance,
        )
        final_servers = allocation.snapshots
        failed_templates = allocation.failed_templates
        server_name = allocation.assignment_map.get(template.id)

        if server_name is not None:
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
                    previous_assignments=previous_assignments,
                    current_assignments=allocation.assignment_map,
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
            states.append(
                SimulationState(
                    step=index,
                    title=f"Add {template.name} -> no fit",
                    latest_placement=None,
                    servers=final_servers,
                )
            )
        previous_assignments = allocation.assignment_map

    if not placements and failed_templates:
        stop_reason = "No server can fit the active reservations in this hour."
    elif failed_templates:
        stop_reason = (
            f"Placed {len(requested_templates) - len(failed_templates)} / {len(requested_templates)} active VMs. "
            f"Unplaced: {', '.join(template.name for template in failed_templates)}."
        )
    else:
        stop_reason = f"Placed all {len(requested_templates)} active VMs."

    summary = _build_summary(
        final_servers=final_servers,
        placements=[item for item in placements if item.step <= len(requested_templates)],
        stop_reason=stop_reason,
        enabled_templates=requested_templates,
        requested_templates=requested_templates,
        failed_templates=failed_templates,
    )
    return HourlySimulation(
        hour=hour,
        label=_hour_label(hour),
        active_vm_names=[template.name for template in requested_templates],
        reserved_vm_names=[template.name for template in enabled_templates],
        placements=placements,
        states=states,
        summary=summary,
    )


def _build_daily_summary(
    enabled_templates: list[VMTemplate],
    hourly_results: list[HourlySimulation],
) -> DailySimulationSummary:
    reservations_by_hour = {
        str(hour): sum(1 for template in enabled_templates if hour in template.active_hours)
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
        reserved_vm_count=len(enabled_templates),
        reservation_slot_count=sum(len(template.active_hours) for template in enabled_templates),
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


def _to_working_server(server: ServerInput) -> _WorkingServer:
    return _WorkingServer(
        name=server.name,
        total_cpu=float(server.cpu_cores),
        total_memory=float(server.memory_gb),
        total_disk=float(server.disk_gb),
        total_gpu=float(server.gpu_count),
        used_cpu=float(server.cpu_used),
        used_memory=float(server.memory_used_gb),
        used_disk=float(server.disk_used_gb),
        used_gpu=float(server.gpu_used),
    )


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


@dataclass
class _AllocationResult:
    snapshots: list[ServerSnapshot]
    assignment_map: dict[str, str]
    failed_templates: list[VMTemplate]


def _rebalance_allocation(
    *,
    base_servers: list[ServerInput],
    templates: list[VMTemplate],
    allow_rebalance: bool,
) -> _AllocationResult:
    working_servers = [_to_working_server(server) for server in base_servers]
    ordered_templates = (
        sorted(templates, key=_template_sort_key, reverse=True)
        if allow_rebalance
        else list(templates)
    )
    assignment_map: dict[str, str] = {}
    failed_templates: list[VMTemplate] = []

    for template in ordered_templates:
        choice = _choose_server(working_servers, template)
        if choice is None:
            failed_templates.append(template)
            continue
        _apply_template(choice, template)
        assignment_map[template.id] = choice.name

    return _AllocationResult(
        snapshots=_snapshot_servers(working_servers),
        assignment_map=assignment_map,
        failed_templates=failed_templates,
    )


def _snapshot_servers(servers: list[_WorkingServer]) -> list[ServerSnapshot]:
    snapshots = [_snapshot_server(server) for server in servers]
    return sorted(snapshots, key=lambda item: item.name)


def _snapshot_server(server: _WorkingServer) -> ServerSnapshot:
    vm_counts = Counter(server.placed_vms)
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
            cpu_cores=round(server.total_cpu - server.used_cpu, 2),
            memory_gb=round(server.total_memory - server.used_memory, 2),
            disk_gb=round(server.total_disk - server.used_disk, 2),
            gpu_count=round(server.total_gpu - server.used_gpu, 2),
        ),
        shares=_server_shares(server),
        dominant_share=round(_dominant_share(server), 4),
        average_share=round(_average_share(server), 4),
        placement_count=server.placement_count,
        placed_vms=list(server.placed_vms),
        vm_stack=[
            VmStackItem(name=name, count=count)
            for name, count in sorted(vm_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )


def _server_shares(server: _WorkingServer) -> ResourceShares:
    return ResourceShares(
        cpu=round(_share(server.used_cpu, server.total_cpu), 4),
        memory=round(_share(server.used_memory, server.total_memory), 4),
        disk=round(_share(server.used_disk, server.total_disk), 4),
        gpu=round(_share(server.used_gpu, server.total_gpu), 4),
    )


def _share(used: float, total: float) -> float:
    if total <= EPSILON:
        return 0.0
    return max(used / total, 0.0)


def _dominant_share(server: _WorkingServer) -> float:
    shares = _share_values(server)
    return max(shares) if shares else 0.0


def _average_share(server: _WorkingServer) -> float:
    shares = _share_values(server)
    return mean(shares) if shares else 0.0


def _share_values(server: _WorkingServer) -> list[float]:
    values = [
        _share(server.used_cpu, server.total_cpu),
        _share(server.used_memory, server.total_memory),
        _share(server.used_disk, server.total_disk),
    ]
    if server.total_gpu > EPSILON:
        values.append(_share(server.used_gpu, server.total_gpu))
    return values


def _can_fit(server: _WorkingServer, template: VMTemplate) -> bool:
    if (server.total_cpu - server.used_cpu) + EPSILON < template.cpu_cores:
        return False
    if (server.total_memory - server.used_memory) + EPSILON < template.memory_gb:
        return False
    if (server.total_disk - server.used_disk) + EPSILON < template.disk_gb:
        return False
    if (server.total_gpu - server.used_gpu) + EPSILON < template.gpu_count:
        return False
    return True


def _choose_server(
    servers: list[_WorkingServer],
    template: VMTemplate,
) -> _WorkingServer | None:
    candidates = [server for server in servers if _can_fit(server, template)]
    if not candidates:
        return None

    return min(
        candidates,
        key=lambda server: (
            _projected_dominant_share(server, template),
            _projected_average_share(server, template),
            server.placement_count,
            server.name,
        ),
    )


def _projected_dominant_share(server: _WorkingServer, template: VMTemplate) -> float:
    return max(_projected_share_values(server, template))


def _projected_average_share(server: _WorkingServer, template: VMTemplate) -> float:
    return mean(_projected_share_values(server, template))


def _projected_share_values(server: _WorkingServer, template: VMTemplate) -> list[float]:
    values = [
        _share(server.used_cpu + template.cpu_cores, server.total_cpu),
        _share(server.used_memory + template.memory_gb, server.total_memory),
        _share(server.used_disk + template.disk_gb, server.total_disk),
    ]
    if server.total_gpu > EPSILON or template.gpu_count > EPSILON:
        values.append(_share(server.used_gpu + template.gpu_count, server.total_gpu))
    return values


def _apply_template(server: _WorkingServer, template: VMTemplate) -> None:
    server.used_cpu += template.cpu_cores
    server.used_memory += template.memory_gb
    server.used_disk += template.disk_gb
    server.used_gpu += template.gpu_count
    server.placed_vms.append(template.name)


def _build_reason(server: _WorkingServer, template: VMTemplate) -> str:
    shares = _server_shares(server)
    return (
        f"Placed on {server.name} because its projected dominant share is lowest. "
        f"After placement: CPU {shares.cpu:.0%}, RAM {shares.memory:.0%}, "
        f"Disk {shares.disk:.0%}, GPU {shares.gpu:.0%}."
    )


def _build_rebalance_reason(
    *,
    template: VMTemplate,
    server_name: str,
    previous_assignments: dict[str, str],
    current_assignments: dict[str, str],
) -> str:
    moved = [
        template_id
        for template_id, previous_server in previous_assignments.items()
        if current_assignments.get(template_id) != previous_server
    ]
    if moved:
        return (
            f"Placed {template.name} on {server_name}. "
            f"Auto-rebalanced {len(moved)} existing VM(s) across the cluster to free space."
        )
    return f"Placed {template.name} on {server_name} using the current cluster balance."


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

    cluster_cpu_total = sum(server.total.cpu_cores for server in final_servers)
    cluster_memory_total = sum(server.total.memory_gb for server in final_servers)
    cluster_disk_total = sum(server.total.disk_gb for server in final_servers)
    cluster_gpu_total = sum(server.total.gpu_count for server in final_servers)

    cluster_cpu_used = sum(server.used.cpu_cores for server in final_servers)
    cluster_memory_used = sum(server.used.memory_gb for server in final_servers)
    cluster_disk_used = sum(server.used.disk_gb for server in final_servers)
    cluster_gpu_used = sum(server.used.gpu_count for server in final_servers)

    cluster_shares = ResourceShares(
        cpu=round(_share(cluster_cpu_used, cluster_cpu_total), 4),
        memory=round(_share(cluster_memory_used, cluster_memory_total), 4),
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
            f"Cluster utilization is CPU {cluster_shares.cpu:.0%}, RAM {cluster_shares.memory:.0%}, "
            f"Disk {cluster_shares.disk:.0%}. "
            + (
                f"The tightest node is {most_loaded.name} at dominant share "
                f"{most_loaded.dominant_share:.0%}."
                if most_loaded is not None
                else "No node state is available."
            )
        )
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
        "cpu": server.shares.cpu,
        "memory": server.shares.memory,
        "disk": server.shares.disk,
        "gpu": server.shares.gpu,
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
