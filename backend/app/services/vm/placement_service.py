from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import uuid

from sqlmodel import Session

from app.ai.pve_advisor import recommendation_service as advisor_service
from app.ai.pve_advisor.schemas import (
    NodeCapacity,
    PlacementDecision,
    PlacementPlan,
    PlacementRequest,
    ResourceType,
)
from app.domain.pve_placement import policy as placement_policy
from app.domain.pve_placement import scorer as placement_scorer
from app.domain.pve_placement.models import (
    DEFAULT_CPU_PEAK_HIGH_SHARE,
    DEFAULT_CPU_PEAK_WARN_SHARE,
    DEFAULT_RAM_PEAK_HIGH_SHARE,
    DEFAULT_RAM_PEAK_WARN_SHARE,
    AssignmentEvaluation as _AssignmentEvaluation,
    NodeScoreBreakdown,
    PlacementTuning as _PlacementTuning,
    StorageSelection as _StorageSelection,
    WorkingStoragePool as _WorkingStoragePool,
)
from app.domain.pve_placement.storage import (
    STORAGE_SPEED_RANK as _STORAGE_SPEED_RANK,
    reserve_storage_pool as _reserve_storage_pool,
    select_best_storage_for_request as _select_best_storage_for_request,
)
from app.models import VMRequest
from app.repositories import proxmox_storage as proxmox_storage_repo
from app.repositories import vm_request as vm_request_repo

GIB = 1024**3
_STORAGE_SPEED_RANK = {"nvme": 0, "ssd": 1, "hdd": 2, "unknown": 3}
DEFAULT_PLACEMENT_STRATEGY = placement_policy.DEFAULT_PLACEMENT_STRATEGY


@dataclass
class CurrentPlacementSelection:
    node: str | None
    strategy: str
    plan: PlacementPlan


_projected_share = placement_scorer.projected_share
_storage_contention_penalty = placement_scorer.storage_contention_penalty
_node_balance_score = placement_scorer.node_balance_score
_peak_penalty = placement_scorer.peak_penalty
_cpu_contention_penalty = placement_scorer.cpu_contention_penalty
_loadavg_penalty = placement_scorer.loadavg_penalty
_reference_loadavg_per_core = placement_scorer.reference_loadavg_per_core
_linear_penalty = placement_scorer.linear_penalty


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _request_window(db_request: VMRequest) -> tuple[datetime | None, datetime | None]:
    return _normalize_datetime(db_request.start_at), _normalize_datetime(db_request.end_at)


def _request_capacity_tuple(db_request: VMRequest) -> tuple[float, int, int]:
    cpu_cores = float(db_request.cores or 1)
    memory_bytes = int(db_request.memory or 512) * 1024 * 1024
    disk_gb = (
        int(db_request.disk_size or 0)
        if db_request.resource_type == "vm"
        else int(db_request.rootfs_size or 0)
    )
    if disk_gb <= 0:
        disk_gb = 20 if db_request.resource_type == "vm" else 8
    return cpu_cores, memory_bytes, disk_gb * GIB


def _get_placement_tuning(*, session: Session) -> _PlacementTuning:
    return placement_policy.get_placement_tuning(session=session)


def _build_storage_pool_state(
    *,
    session: Session,
    node_names: list[str],
) -> tuple[dict[str, list[_WorkingStoragePool]], bool]:
    storages = proxmox_storage_repo.get_all_storages(session)
    if not storages:
        return {node_name: [] for node_name in node_names}, False

    shared_registry: dict[str, _WorkingStoragePool] = {}
    by_node: dict[str, list[_WorkingStoragePool]] = {node_name: [] for node_name in node_names}
    node_set = set(node_names)

    for storage in storages:
        node_name = str(storage.node_name or "")
        if node_name not in node_set:
            continue

        if storage.is_shared:
            pool = shared_registry.get(storage.storage)
            if pool is None:
                pool = _WorkingStoragePool(
                    storage=storage.storage,
                    total_gb=float(storage.total_gb or 0.0),
                    avail_gb=float(storage.avail_gb or 0.0),
                    active=bool(storage.active),
                    enabled=bool(storage.enabled),
                    can_vm=bool(storage.can_vm),
                    can_lxc=bool(storage.can_lxc),
                    is_shared=bool(storage.is_shared),
                    speed_tier=str(storage.speed_tier or "unknown"),
                    user_priority=int(storage.user_priority or 5),
                )
                shared_registry[storage.storage] = pool
            by_node[node_name].append(pool)
            continue

        by_node[node_name].append(
            _WorkingStoragePool(
                storage=storage.storage,
                total_gb=float(storage.total_gb or 0.0),
                avail_gb=float(storage.avail_gb or 0.0),
                active=bool(storage.active),
                enabled=bool(storage.enabled),
                can_vm=bool(storage.can_vm),
                can_lxc=bool(storage.can_lxc),
                is_shared=bool(storage.is_shared),
                speed_tier=str(storage.speed_tier or "unknown"),
                user_priority=int(storage.user_priority or 5),
            )
        )

    has_managed_storage = any(pools for pools in by_node.values())
    return by_node, has_managed_storage


def _provisioned_current_node(request: VMRequest) -> str | None:
    if request.vmid is None:
        return None
    current = str(request.actual_node or "").strip()
    if current:
        return current
    assigned = str(request.assigned_node or "").strip()
    return assigned or None


def _build_rebalance_baseline_nodes(
    *,
    session: Session,
    requests: list[VMRequest],
) -> list[NodeCapacity]:
    nodes, resources = advisor_service._load_cluster_state()
    cpu_overcommit_ratio, disk_overcommit_ratio = get_overcommit_ratios(session)
    working_nodes = advisor_service._build_node_capacities(
        nodes=nodes,
        resources=resources,
        cpu_overcommit_ratio=cpu_overcommit_ratio,
        disk_overcommit_ratio=disk_overcommit_ratio,
    )
    for request in requests:
        if request.vmid is not None:
            _release_request_from_capacities(
                node_capacities=working_nodes,
                db_request=request,
                node_name=str(request.actual_node or request.assigned_node or ""),
            )
    return working_nodes


def _build_preview_vm_request(
    *,
    request: PlacementRequest,
    start_at: datetime,
    end_at: datetime,
) -> VMRequest:
    is_vm = str(request.resource_type) == "vm"
    return VMRequest(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        reason="placement-preview",
        resource_type=str(request.resource_type),
        hostname="placement-preview",
        cores=int(request.cpu_cores or 1),
        memory=int(request.memory_mb or 512),
        password="preview",
        storage="preview",
        environment_type="Preview",
        start_at=start_at,
        end_at=end_at,
        ostemplate=None if is_vm else "preview",
        rootfs_size=None if is_vm else int(request.disk_gb or 0),
        unprivileged=True,
        template_id=1 if is_vm else None,
        disk_size=int(request.disk_gb or 0) if is_vm else None,
        username="preview" if is_vm else None,
        created_at=_utc_now(),
    )


def _refresh_node_candidate(node: NodeCapacity) -> None:
    node.guest_pressure_ratio = advisor_service._guest_pressure_ratio(
        int(node.running_resources),
        int(node.total_cpu_cores),
    )
    node.guest_overloaded = (
        node.guest_pressure_ratio >= advisor_service.settings.guest_pressure_threshold
    )
    node.candidate = (
        node.status == "online"
        and node.allocatable_cpu_cores > 0
        and node.allocatable_memory_bytes > 0
        and node.allocatable_disk_bytes > 0
        and not node.guest_overloaded
    )


def _release_request_from_capacities(
    *,
    node_capacities: list[NodeCapacity],
    db_request: VMRequest,
    node_name: str | None,
) -> None:
    if not node_name:
        return
    node = next((item for item in node_capacities if item.node == node_name), None)
    if node is None:
        return

    cpu_cores, memory_bytes, disk_bytes = _request_capacity_tuple(db_request)
    node.allocatable_cpu_cores = min(
        round(node.allocatable_cpu_cores + cpu_cores, 2),
        round(float(node.total_cpu_cores), 2),
    )
    node.allocatable_memory_bytes = min(
        node.allocatable_memory_bytes + memory_bytes,
        int(node.total_memory_bytes),
    )
    node.allocatable_disk_bytes = min(
        node.allocatable_disk_bytes + disk_bytes,
        int(node.total_disk_bytes),
    )
    node.running_resources = max(int(node.running_resources) - 1, 0)
    _refresh_node_candidate(node)


def _reserve_request_on_capacities(
    *,
    node_capacities: list[NodeCapacity],
    db_request: VMRequest,
    node_name: str,
) -> None:
    node = next((item for item in node_capacities if item.node == node_name), None)
    if node is None:
        raise ValueError(f"Target node {node_name} not found in capacity list")

    cpu_cores, memory_bytes, disk_bytes = _request_capacity_tuple(db_request)
    node.allocatable_cpu_cores = max(
        round(node.allocatable_cpu_cores - cpu_cores, 2),
        0.0,
    )
    node.allocatable_memory_bytes = max(node.allocatable_memory_bytes - memory_bytes, 0)
    node.allocatable_disk_bytes = max(node.allocatable_disk_bytes - disk_bytes, 0)
    node.running_resources = int(node.running_resources) + 1
    _refresh_node_candidate(node)


def _hour_window_iter(start_at: datetime, end_at: datetime) -> list[datetime]:
    if end_at <= start_at:
        return [start_at]
    cursor = start_at.replace(minute=0, second=0, microsecond=0)
    if cursor < start_at:
        cursor += timedelta(hours=1)
    checkpoints: list[datetime] = []
    while cursor < end_at:
        checkpoints.append(cursor)
        cursor += timedelta(hours=1)
    return checkpoints or [start_at]


def _apply_reserved_requests_to_capacities(
    *,
    baseline_capacities,
    reserved_requests: list[VMRequest],
    at_time: datetime,
):
    adjusted = [item.model_copy(deep=True) for item in baseline_capacities]
    by_node = {item.node: item for item in adjusted}

    for reserved in reserved_requests:
        reserved_start = _normalize_datetime(reserved.start_at)
        reserved_end = _normalize_datetime(reserved.end_at)
        assigned_node = str(reserved.assigned_node or "")
        if not reserved_start or not reserved_end or not assigned_node:
            continue
        if not (reserved_start <= at_time < reserved_end):
            continue

        node = by_node.get(assigned_node)
        if not node:
            continue

        reserved_cpu, reserved_memory, reserved_disk = _request_capacity_tuple(reserved)
        node.allocatable_cpu_cores = max(node.allocatable_cpu_cores - reserved_cpu, 0.0)
        node.allocatable_memory_bytes = max(node.allocatable_memory_bytes - reserved_memory, 0)
        node.allocatable_disk_bytes = max(node.allocatable_disk_bytes - reserved_disk, 0)
        node.candidate = (
            node.status == "online"
            and node.allocatable_cpu_cores > 0
            and node.allocatable_memory_bytes > 0
            and node.allocatable_disk_bytes > 0
        )

    return adjusted


def build_plan(
    *,
    session: Session,
    request: PlacementRequest,
    node_capacities: list[NodeCapacity],
    effective_resource_type: ResourceType,
    resource_type_reason: str,
    placement_strategy: str | None = None,
    node_priorities: dict[str, int] | None = None,
    current_node: str | None = None,
) -> PlacementPlan:
    strategy = _normalize_strategy(placement_strategy or get_placement_strategy(session))
    priorities = node_priorities or get_node_priorities(session)
    tuning = _get_placement_tuning(session=session)
    working_nodes = [item.model_copy(deep=True) for item in node_capacities]
    storage_pools_by_node, has_managed_storage = _build_storage_pool_state(
        session=session,
        node_names=[item.node for item in working_nodes],
    )
    _, disk_overcommit_ratio = get_overcommit_ratios(session)
    required_cpu = advisor_service._effective_cpu_cores(request, effective_resource_type)
    required_memory = advisor_service._effective_memory_bytes(request, effective_resource_type)
    required_disk = request.disk_gb * GIB
    placements: dict[str, int] = {item.node: 0 for item in working_nodes}
    remaining = request.instance_count

    while remaining > 0:
        candidates: list[tuple[NodeCapacity, _StorageSelection | None]] = []
        for item in working_nodes:
            if not item.candidate or not advisor_service._can_fit(
                item,
                cores=required_cpu,
                memory_bytes=required_memory,
                disk_bytes=required_disk,
                gpu_required=request.gpu_required,
            ):
                continue

            storage_selection: _StorageSelection | None = None
            if has_managed_storage:
                storage_selection = _select_best_storage_for_request(
                    storage_pools=storage_pools_by_node.get(item.node, []),
                    resource_type=str(request.resource_type),
                    disk_gb=int(request.disk_gb),
                    disk_overcommit_ratio=disk_overcommit_ratio,
                    tuning=tuning,
                )
                if storage_selection is None:
                    continue

            candidates.append((item, storage_selection))
        if not candidates:
            break

        chosen, chosen_storage = min(
            candidates,
            key=lambda candidate: _placement_sort_key(
                candidate[0],
                placements=placements,
                priorities=priorities,
                strategy=strategy,
                cores=required_cpu,
                memory_bytes=required_memory,
                disk_bytes=required_disk,
                storage_selection=candidate[1],
                tuning=tuning,
                current_node=current_node,
            ),
        )
        placements[chosen.node] += 1
        chosen.allocatable_cpu_cores = max(
            chosen.allocatable_cpu_cores - required_cpu,
            0.0,
        )
        chosen.allocatable_memory_bytes = max(
            chosen.allocatable_memory_bytes - required_memory,
            0,
        )
        chosen.allocatable_disk_bytes = max(
            chosen.allocatable_disk_bytes - required_disk,
            0,
        )
        chosen.running_resources += 1
        chosen.guest_pressure_ratio = advisor_service._guest_pressure_ratio(
            chosen.running_resources,
            int(chosen.total_cpu_cores),
        )
        chosen.guest_overloaded = (
            chosen.guest_pressure_ratio
            >= advisor_service.settings.guest_pressure_threshold
        )
        chosen.candidate = (
            chosen.status == "online"
            and chosen.allocatable_cpu_cores > 0
            and chosen.allocatable_memory_bytes > 0
            and chosen.allocatable_disk_bytes > 0
            and not chosen.guest_overloaded
        )
        if chosen_storage is not None:
            _reserve_storage_pool(
                selection=chosen_storage,
                disk_gb=int(request.disk_gb),
                disk_overcommit_ratio=disk_overcommit_ratio,
            )
        remaining -= 1

    assigned = request.instance_count - remaining
    placement_decisions = [
        PlacementDecision(
            node=item.node,
            instance_count=placements[item.node],
            cpu_cores_reserved=round(placements[item.node] * required_cpu, 2),
            memory_bytes_reserved=placements[item.node] * required_memory,
            disk_bytes_reserved=placements[item.node] * required_disk,
            remaining_cpu_cores=round(item.allocatable_cpu_cores, 2),
            remaining_memory_bytes=item.allocatable_memory_bytes,
            remaining_disk_bytes=item.allocatable_disk_bytes,
        )
        for item in working_nodes
        if placements[item.node] > 0
    ]
    placement_decisions.sort(key=lambda item: (-item.instance_count, item.node))

    return PlacementPlan(
        feasible=remaining == 0,
        requested_resource_type=request.resource_type,
        effective_resource_type=effective_resource_type,
        resource_type_reason=resource_type_reason,
        assigned_instances=assigned,
        unassigned_instances=remaining,
        recommended_node=placement_decisions[0].node if placement_decisions else None,
        summary=advisor_service._build_summary_text(
            request=request,
            placement_decisions=placement_decisions,
            effective_resource_type=effective_resource_type,
            assigned=assigned,
            remaining=remaining,
        ),
        rationale=advisor_service._build_rationale(
            request=request,
            placement_decisions=placement_decisions,
            effective_resource_type=effective_resource_type,
            node_capacities=node_capacities,
        ),
        warnings=advisor_service._build_warnings(
            node_capacities=node_capacities,
            request=request,
            effective_resource_type=effective_resource_type,
            remaining=remaining,
        ),
        placements=placement_decisions,
        candidate_nodes=node_capacities,
    )


def select_current_target_node(
    *,
    session: Session,
    db_request: VMRequest,
) -> CurrentPlacementSelection:
    request = _to_placement_request(db_request)
    nodes, resources = advisor_service._load_cluster_state()
    cpu_overcommit_ratio, disk_overcommit_ratio = get_overcommit_ratios(session)
    node_capacities = advisor_service._build_node_capacities(
        nodes=nodes,
        resources=resources,
        cpu_overcommit_ratio=cpu_overcommit_ratio,
        disk_overcommit_ratio=disk_overcommit_ratio,
    )
    effective_resource_type, resource_type_reason = advisor_service._decide_resource_type(
        request
    )
    plan = build_plan(
        session=session,
        request=request,
        node_capacities=node_capacities,
        effective_resource_type=effective_resource_type,
        resource_type_reason=resource_type_reason,
    )
    return CurrentPlacementSelection(
        node=plan.recommended_node,
        strategy=get_placement_strategy(session),
        plan=plan,
    )


def select_reserved_target_node(
    *,
    session: Session,
    db_request: VMRequest,
    reserved_requests: list[VMRequest] | None = None,
) -> CurrentPlacementSelection:
    start_at, end_at = _request_window(db_request)
    return select_reserved_target_node_for_request(
        session=session,
        request=_to_placement_request(db_request),
        start_at=start_at,
        end_at=end_at,
        reserved_requests=reserved_requests,
    )


def select_reserved_target_node_for_request(
    *,
    session: Session,
    request: PlacementRequest,
    start_at: datetime | None,
    end_at: datetime | None,
    reserved_requests: list[VMRequest] | None = None,
) -> CurrentPlacementSelection:
    if not start_at or not end_at:
        nodes, resources = advisor_service._load_cluster_state()
        cpu_overcommit_ratio, disk_overcommit_ratio = get_overcommit_ratios(session)
        node_capacities = advisor_service._build_node_capacities(
            nodes=nodes,
            resources=resources,
            cpu_overcommit_ratio=cpu_overcommit_ratio,
            disk_overcommit_ratio=disk_overcommit_ratio,
        )
        effective_resource_type, resource_type_reason = (
            advisor_service._decide_resource_type(request)
        )
        plan = build_plan(
            session=session,
            request=request,
            node_capacities=node_capacities,
            effective_resource_type=effective_resource_type,
            resource_type_reason=resource_type_reason,
        )
        return CurrentPlacementSelection(
            node=plan.recommended_node,
            strategy=get_placement_strategy(session),
            plan=plan,
        )

    nodes, resources = advisor_service._load_cluster_state()
    cpu_overcommit_ratio, disk_overcommit_ratio = get_overcommit_ratios(session)
    baseline_capacities = advisor_service._build_node_capacities(
        nodes=nodes,
        resources=resources,
        cpu_overcommit_ratio=cpu_overcommit_ratio,
        disk_overcommit_ratio=disk_overcommit_ratio,
    )
    effective_resource_type, resource_type_reason = advisor_service._decide_resource_type(
        request
    )
    if reserved_requests is None:
        reserved_requests = vm_request_repo.get_approved_vm_requests_overlapping_window(
            session=session,
            window_start=start_at,
            window_end=end_at,
        )
    checkpoints = [start_at] + [
        checkpoint
        for checkpoint in _hour_window_iter(start_at, end_at)
        if checkpoint != start_at
    ]

    feasible_nodes = {item.node for item in baseline_capacities}
    start_capacities = baseline_capacities

    for index, checkpoint in enumerate(checkpoints):
        adjusted_capacities = _apply_reserved_requests_to_capacities(
            baseline_capacities=baseline_capacities,
            reserved_requests=reserved_requests,
            at_time=checkpoint,
        )
        if index == 0:
            start_capacities = adjusted_capacities

        hour_feasible_nodes = {
            item.node
            for item in adjusted_capacities
            if advisor_service._can_fit(
                item,
                cores=advisor_service._effective_cpu_cores(
                    request, effective_resource_type
                ),
                memory_bytes=advisor_service._effective_memory_bytes(
                    request, effective_resource_type
                ),
                disk_bytes=request.disk_gb * GIB,
                gpu_required=request.gpu_required,
            )
        }
        feasible_nodes &= hour_feasible_nodes
        if not feasible_nodes:
            break

    strategy = get_placement_strategy(session)
    if not feasible_nodes:
        return CurrentPlacementSelection(
            node=None,
            strategy=strategy,
            plan=build_plan(
                session=session,
                request=request,
                node_capacities=[],
                effective_resource_type=effective_resource_type,
                resource_type_reason=resource_type_reason,
                placement_strategy=strategy,
                node_priorities=get_node_priorities(session),
            ),
        )

    filtered_start_capacities = [
        item for item in start_capacities if item.node in feasible_nodes
    ]
    plan = build_plan(
        session=session,
        request=request,
        node_capacities=filtered_start_capacities,
        effective_resource_type=effective_resource_type,
        resource_type_reason=resource_type_reason,
        placement_strategy=strategy,
        node_priorities=get_node_priorities(session),
    )
    overlapping_start_requests = [
        item
        for item in reserved_requests
        if (window := _request_window(item))[0] is not None
        and window[1] is not None
        and window[0] <= start_at < window[1]
    ]
    preview_request = _build_preview_vm_request(
        request=request,
        start_at=start_at,
        end_at=end_at,
    )
    preview_cohort = overlapping_start_requests + [preview_request]
    preview_ordered_requests = sorted(
        preview_cohort,
        key=lambda item: (
            _normalize_datetime(item.start_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.reviewed_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.created_at) or datetime.min.replace(tzinfo=UTC),
            str(item.id),
        ),
    )
    preview_baseline_nodes = _build_rebalance_baseline_nodes(
        session=session,
        requests=preview_ordered_requests,
    )
    preview_baseline_nodes = [
        item.model_copy(deep=True)
        for item in preview_baseline_nodes
        if item.node in feasible_nodes
    ]
    priorities = get_node_priorities(session)
    tuning = _get_placement_tuning(session=session)
    best_preview_node = plan.recommended_node
    best_preview_objective: tuple[float, float, float, int] | None = None
    candidate_evals: dict[str, _AssignmentEvaluation] = {}
    for candidate_node in sorted(feasible_nodes):
        try:
            preview_assignments = _solve_rebalance_assignments(
                session=session,
                ordered_requests=preview_ordered_requests,
                baseline_nodes=preview_baseline_nodes,
                strategy=strategy,
                priorities=priorities,
                tuning=tuning,
                fixed_assignments={preview_request.id: candidate_node},
            )
            preview_eval = _evaluate_active_assignment_map(
                session=session,
                ordered_requests=preview_ordered_requests,
                baseline_nodes=preview_baseline_nodes,
                assignments=preview_assignments,
                priorities=priorities,
                tuning=tuning,
            )
        except ValueError:
            continue
        if not preview_eval.feasible:
            continue
        candidate_evals[candidate_node] = preview_eval
        if (
            best_preview_objective is None
            or preview_eval.objective < best_preview_objective
        ):
            best_preview_objective = preview_eval.objective
            best_preview_node = candidate_node
    preview_reasons = (
        _build_preview_selection_reasons(
            selected_node=best_preview_node,
            selected_eval=candidate_evals[best_preview_node],
            candidate_evals=candidate_evals,
            priorities=priorities,
        )
        if best_preview_node and best_preview_node in candidate_evals
        else list(plan.rationale or [])
    )
    return CurrentPlacementSelection(
        node=best_preview_node,
        strategy=strategy,
        plan=plan.model_copy(
            update={
                "recommended_node": best_preview_node,
                "summary": (
                    "Reservation preview selected the best feasible node "
                    "using the same active-window rebalance objective."
                ),
                "rationale": preview_reasons,
            }
        ),
    )


def _evaluate_active_assignment_map(
    *,
    session: Session,
    ordered_requests: list[VMRequest],
    baseline_nodes: list[NodeCapacity],
    assignments: dict[uuid.UUID, str],
    priorities: dict[str, int],
    tuning: _PlacementTuning,
) -> _AssignmentEvaluation:
    working_nodes = [item.model_copy(deep=True) for item in baseline_nodes]
    by_node = {item.node: item for item in working_nodes}
    storage_pools_by_node, has_managed_storage = _build_storage_pool_state(
        session=session,
        node_names=[item.node for item in working_nodes],
    )
    _, disk_overcommit_ratio = get_overcommit_ratios(session)
    storage_penalty_total = 0.0
    priority_total = 0.0
    movement_count = 0

    for request in ordered_requests:
        target_node = assignments.get(request.id)
        if not target_node:
            return _AssignmentEvaluation(
                feasible=False,
                objective=(float("inf"), float("inf"), 10**9, float("inf")),
            )
        node = by_node.get(target_node)
        if node is None:
            return _AssignmentEvaluation(
                feasible=False,
                objective=(float("inf"), float("inf"), 10**9, float("inf")),
            )

        placement_request = _to_placement_request(request)
        effective_resource_type, _ = advisor_service._decide_resource_type(
            placement_request
        )
        required_cpu = advisor_service._effective_cpu_cores(
            placement_request,
            effective_resource_type,
        )
        required_memory = advisor_service._effective_memory_bytes(
            placement_request,
            effective_resource_type,
        )
        required_disk = placement_request.disk_gb * GIB
        if not node.candidate or not advisor_service._can_fit(
            node,
            cores=required_cpu,
            memory_bytes=required_memory,
            disk_bytes=required_disk,
            gpu_required=placement_request.gpu_required,
        ):
            return _AssignmentEvaluation(
                feasible=False,
                objective=(float("inf"), float("inf"), 10**9, float("inf")),
            )

        storage_selection: _StorageSelection | None = None
        if has_managed_storage:
            storage_selection = _select_best_storage_for_request(
                storage_pools=storage_pools_by_node.get(target_node, []),
                resource_type=str(placement_request.resource_type),
                disk_gb=int(placement_request.disk_gb),
                disk_overcommit_ratio=disk_overcommit_ratio,
                tuning=tuning,
            )
            if storage_selection is None:
                return _AssignmentEvaluation(
                    feasible=False,
                    objective=(float("inf"), float("inf"), 10**9, float("inf")),
                )

        _reserve_request_on_capacities(
            node_capacities=working_nodes,
            db_request=request,
            node_name=target_node,
        )
        if storage_selection is not None:
            _reserve_storage_pool(
                selection=storage_selection,
                disk_gb=int(placement_request.disk_gb),
                disk_overcommit_ratio=disk_overcommit_ratio,
            )
            storage_penalty_total += storage_selection.contention_penalty
        priority_total += float(priorities.get(target_node, 5))
        if _provisioned_current_node(request) not in {None, target_node}:
            movement_count += 1

    node_score_map = {
        node.node: _node_balance_score(node, tuning=tuning) for node in working_nodes
    }
    max_node_score = max(node_score_map.values(), default=0.0)
    total_score = (
        sum(node_score_map.values())
        + (storage_penalty_total * tuning.disk_penalty_weight)
        + (movement_count * tuning.migration_cost)
    )
    return _AssignmentEvaluation(
        feasible=True,
        objective=(max_node_score, total_score, priority_total, movement_count),
        max_node_score=max_node_score,
        total_score=total_score,
        priority_total=priority_total,
        movement_count=movement_count,
        node_scores=node_score_map,
        storage_penalties={
            node_name: sum(
                _storage_contention_penalty(
                    projected_share=_projected_share(
                        used=max(pool.total_gb - pool.avail_gb, 0.0),
                        total=max(pool.total_gb, 1.0),
                    ),
                    placed_count=pool.placed_count,
                    overcommit_placed_count=pool.overcommit_placed_count,
                    tuning=tuning,
                    overcommit=pool.overcommit_placed_count > 0,
                )
                for pool in storage_pools_by_node.get(node_name, [])
            )
            for node_name in by_node
        },
    )


def _initial_active_assignment_map(
    *,
    session: Session,
    ordered_requests: list[VMRequest],
    baseline_nodes: list[NodeCapacity],
    strategy: str,
    priorities: dict[str, int],
    tuning: _PlacementTuning,
    fixed_assignments: dict[uuid.UUID, str] | None = None,
) -> dict[uuid.UUID, str]:
    working_nodes = [item.model_copy(deep=True) for item in baseline_nodes]
    storage_pools_by_node, has_managed_storage = _build_storage_pool_state(
        session=session,
        node_names=[item.node for item in working_nodes],
    )
    _, disk_overcommit_ratio = get_overcommit_ratios(session)
    placements: dict[str, int] = {item.node: 0 for item in working_nodes}
    assignments: dict[uuid.UUID, str] = {}
    locked_nodes = fixed_assignments or {}

    for request in ordered_requests:
        placement_request = _to_placement_request(request)
        effective_resource_type, resource_type_reason = advisor_service._decide_resource_type(
            placement_request
        )
        required_cpu = advisor_service._effective_cpu_cores(
            placement_request,
            effective_resource_type,
        )
        required_memory = advisor_service._effective_memory_bytes(
            placement_request,
            effective_resource_type,
        )
        required_disk = placement_request.disk_gb * GIB
        candidates: list[tuple[NodeCapacity, _StorageSelection | None]] = []
        for item in working_nodes:
            forced_node = locked_nodes.get(request.id)
            if forced_node and item.node != forced_node:
                continue
            if not item.candidate or not advisor_service._can_fit(
                item,
                cores=required_cpu,
                memory_bytes=required_memory,
                disk_bytes=required_disk,
                gpu_required=placement_request.gpu_required,
            ):
                continue

            storage_selection: _StorageSelection | None = None
            if has_managed_storage:
                storage_selection = _select_best_storage_for_request(
                    storage_pools=storage_pools_by_node.get(item.node, []),
                    resource_type=str(placement_request.resource_type),
                    disk_gb=int(placement_request.disk_gb),
                    disk_overcommit_ratio=disk_overcommit_ratio,
                    tuning=tuning,
                )
                if storage_selection is None:
                    continue
            candidates.append((item, storage_selection))

        if not candidates:
            # Try relief relocation before giving up
            relief = _try_relief_relocation(
                session=session,
                stuck_request=request,
                ordered_requests_so_far=[r for r in ordered_requests if r.id in assignments],
                current_assignments=assignments,
                working_nodes=working_nodes,
                storage_pools_by_node=storage_pools_by_node,
                has_managed_storage=has_managed_storage,
                strategy=strategy,
                priorities=priorities,
                tuning=tuning,
                locked_request_ids=set(locked_nodes.keys()),
                disk_overcommit_ratio=disk_overcommit_ratio,
            )
            if relief is not None:
                # Adopt the relief assignments and continue
                assignments = relief
                # Re-build working state for the relief assignments
                working_nodes_copy = [item.model_copy(deep=True) for item in baseline_nodes]
                for r in ordered_requests:
                    if r.id in assignments:
                        _reserve_request_on_capacities(
                            node_capacities=working_nodes_copy,
                            db_request=r,
                            node_name=assignments[r.id],
                        )
                working_nodes = working_nodes_copy
                placements = {item.node: 0 for item in working_nodes}
                for node_name in assignments.values():
                    placements[node_name] = placements.get(node_name, 0) + 1
                continue
            raise ValueError(f"No feasible active rebalance exists for request {request.id}")

        chosen, chosen_storage = min(
            candidates,
            key=lambda candidate: _placement_sort_key(
                candidate[0],
                placements=placements,
                priorities=priorities,
                strategy=strategy,
                cores=required_cpu,
                memory_bytes=required_memory,
                disk_bytes=required_disk,
                storage_selection=candidate[1],
                tuning=tuning,
                current_node=_provisioned_current_node(request),
            ),
        )
        assignments[request.id] = chosen.node
        placements[chosen.node] += 1
        _reserve_request_on_capacities(
            node_capacities=working_nodes,
            db_request=request,
            node_name=chosen.node,
        )
        if chosen_storage is not None:
            _reserve_storage_pool(
                selection=chosen_storage,
                disk_gb=int(placement_request.disk_gb),
                disk_overcommit_ratio=disk_overcommit_ratio,
            )

    return assignments


def _run_local_rebalance_search(
    *,
    session: Session,
    ordered_requests: list[VMRequest],
    baseline_nodes: list[NodeCapacity],
    initial_assignments: dict[uuid.UUID, str],
    priorities: dict[str, int],
    tuning: _PlacementTuning,
    locked_request_ids: set[uuid.UUID] | None = None,
) -> dict[uuid.UUID, str]:
    if tuning.search_depth <= 0 or tuning.search_max_relocations <= 0:
        return initial_assignments

    current_assignments = dict(initial_assignments)
    locked_ids = set(locked_request_ids or ())
    # Also lock requests that are migration-pinned
    for req in ordered_requests:
        if getattr(req, 'migration_pinned', False):
            locked_ids.add(req.id)
    current_eval = _evaluate_active_assignment_map(
        session=session,
        ordered_requests=ordered_requests,
        baseline_nodes=baseline_nodes,
        assignments=current_assignments,
        priorities=priorities,
        tuning=tuning,
    )
    if not current_eval.feasible:
        return initial_assignments

    node_names = [item.node for item in baseline_nodes]
    used_moves = 0

    for _ in range(tuning.search_depth):
        if used_moves >= tuning.search_max_relocations:
            break

        best_assignments: dict[uuid.UUID, str] | None = None
        best_eval: _AssignmentEvaluation | None = None
        best_move_cost = 0

        for request in ordered_requests:
            if request.id in locked_ids:
                continue
            current_node = current_assignments.get(request.id)
            if not current_node:
                continue
            for candidate_node in node_names:
                if candidate_node == current_node:
                    continue
                trial_assignments = dict(current_assignments)
                trial_assignments[request.id] = candidate_node
                trial_eval = _evaluate_active_assignment_map(
                    session=session,
                    ordered_requests=ordered_requests,
                    baseline_nodes=baseline_nodes,
                    assignments=trial_assignments,
                    priorities=priorities,
                    tuning=tuning,
                )
                if not trial_eval.feasible or trial_eval.objective >= current_eval.objective:
                    continue
                if best_eval is None or trial_eval.objective < best_eval.objective:
                    best_assignments = trial_assignments
                    best_eval = trial_eval
                    best_move_cost = 1

        if used_moves + 2 <= tuning.search_max_relocations:
            for index, request_a in enumerate(ordered_requests):
                if request_a.id in locked_ids:
                    continue
                node_a = current_assignments.get(request_a.id)
                if not node_a:
                    continue
                for request_b in ordered_requests[index + 1 :]:
                    if request_b.id in locked_ids:
                        continue
                    node_b = current_assignments.get(request_b.id)
                    if not node_b or node_a == node_b:
                        continue
                    trial_assignments = dict(current_assignments)
                    trial_assignments[request_a.id] = node_b
                    trial_assignments[request_b.id] = node_a
                    trial_eval = _evaluate_active_assignment_map(
                        session=session,
                        ordered_requests=ordered_requests,
                        baseline_nodes=baseline_nodes,
                        assignments=trial_assignments,
                        priorities=priorities,
                        tuning=tuning,
                    )
                    if not trial_eval.feasible or trial_eval.objective >= current_eval.objective:
                        continue
                    if best_eval is None or trial_eval.objective < best_eval.objective:
                        best_assignments = trial_assignments
                        best_eval = trial_eval
                        best_move_cost = 2

        if best_assignments is None or best_eval is None:
            break
        current_assignments = best_assignments
        current_eval = best_eval
        used_moves += best_move_cost

    return current_assignments


_RELIEF_MAX_EVALUATIONS = 50


def _try_relief_relocation(
    *,
    session: Session,
    stuck_request: VMRequest,
    ordered_requests_so_far: list[VMRequest],
    current_assignments: dict[uuid.UUID, str],
    working_nodes: list[NodeCapacity],
    storage_pools_by_node: dict[str, list[_WorkingStoragePool]],
    has_managed_storage: bool,
    strategy: str,
    priorities: dict[str, int],
    tuning: _PlacementTuning,
    locked_request_ids: set[uuid.UUID],
    disk_overcommit_ratio: float,
) -> dict[uuid.UUID, str] | None:
    """Try 1-move or 2-move relief to make room for a stuck request.

    When direct placement fails, this function tries moving existing requests
    to other nodes to free capacity for the stuck request.
    Returns updated assignment map or None if no relief found.
    """
    if tuning.search_max_relocations <= 0:
        return None

    stuck_placement = _to_placement_request(stuck_request)
    effective_type, _ = advisor_service._decide_resource_type(stuck_placement)
    required_cpu = advisor_service._effective_cpu_cores(stuck_placement, effective_type)
    required_memory = advisor_service._effective_memory_bytes(stuck_placement, effective_type)
    required_disk = stuck_placement.disk_gb * GIB

    node_names = [n.node for n in working_nodes]
    evaluations = 0
    best_result: dict[uuid.UUID, str] | None = None
    best_score: tuple | None = None

    # 1-move relief: move one request away from a node, then check if stuck_request fits
    for req in ordered_requests_so_far:
        if req.id in locked_request_ids:
            continue
        if evaluations >= _RELIEF_MAX_EVALUATIONS:
            break

        current_node = current_assignments.get(req.id)
        if not current_node:
            continue

        for target_node in node_names:
            if target_node == current_node:
                continue
            if evaluations >= _RELIEF_MAX_EVALUATIONS:
                break
            evaluations += 1

            # Trial: move req from current_node to target_node
            trial = dict(current_assignments)
            trial[req.id] = target_node

            # Check if stuck_request now fits on current_node (freed capacity)
            trial[stuck_request.id] = current_node

            # Validate the entire assignment
            all_requests = ordered_requests_so_far + [stuck_request]
            try:
                trial_eval = _evaluate_active_assignment_map(
                    session=session,
                    ordered_requests=all_requests,
                    baseline_nodes=working_nodes,
                    assignments=trial,
                    priorities=priorities,
                    tuning=tuning,
                )
            except (ValueError, KeyError):
                continue

            if not trial_eval.feasible:
                continue

            if best_score is None or trial_eval.objective < best_score:
                best_score = trial_eval.objective
                best_result = trial

    return best_result


def _solve_rebalance_assignments(
    *,
    session: Session,
    ordered_requests: list[VMRequest],
    baseline_nodes: list[NodeCapacity],
    strategy: str,
    priorities: dict[str, int],
    tuning: _PlacementTuning,
    fixed_assignments: dict[uuid.UUID, str] | None = None,
) -> dict[uuid.UUID, str]:
    initial_assignments = _initial_active_assignment_map(
        session=session,
        ordered_requests=ordered_requests,
        baseline_nodes=baseline_nodes,
        strategy=strategy,
        priorities=priorities,
        tuning=tuning,
        fixed_assignments=fixed_assignments,
    )
    final_assignments = _run_local_rebalance_search(
        session=session,
        ordered_requests=ordered_requests,
        baseline_nodes=baseline_nodes,
        initial_assignments=initial_assignments,
        priorities=priorities,
        tuning=tuning,
        locked_request_ids=(
            set((fixed_assignments or {}).keys())
            | {r.id for r in ordered_requests if getattr(r, 'migration_pinned', False)}
        ),
    )
    final_eval = _evaluate_active_assignment_map(
        session=session,
        ordered_requests=ordered_requests,
        baseline_nodes=baseline_nodes,
        assignments=final_assignments,
        priorities=priorities,
        tuning=tuning,
    )
    if not final_eval.feasible:
        raise ValueError("No feasible active rebalance exists for the current request cohort")
    return final_assignments


def _build_preview_selection_reasons(
    *,
    selected_node: str,
    selected_eval: _AssignmentEvaluation,
    candidate_evals: dict[str, _AssignmentEvaluation],
    priorities: dict[str, int],
) -> list[str]:
    alternatives = [
        (node, evaluation)
        for node, evaluation in candidate_evals.items()
        if node != selected_node and evaluation.feasible
    ]
    if not alternatives:
        return [f"因為 {selected_node} 是目前這個時段唯一可行的節點。"]

    runner_up_node, runner_up_eval = min(alternatives, key=lambda item: item[1].objective)
    reasons = [
        (
            f"因為把本次申請放在 {selected_node}，可以讓這個時段整體 cohort "
            "的最大節點負載分數更低。"
        )
    ]

    if selected_eval.max_node_score + 0.01 < runner_up_eval.max_node_score:
        bottleneck_node = max(
            (runner_up_eval.node_scores or {}).items(),
            key=lambda item: item[1],
            default=(runner_up_node, runner_up_eval.max_node_score),
        )[0]
        reasons.append(f"因為可降低 {bottleneck_node} 的整體負載尖峰風險。")

    selected_storage_penalty = (selected_eval.storage_penalties or {}).get(selected_node, 0.0)
    runner_up_storage_penalty = (runner_up_eval.storage_penalties or {}).get(
        runner_up_node,
        0.0,
    )
    if selected_storage_penalty + 0.08 < runner_up_storage_penalty:
        reasons.append(
            f"因為 {selected_node} 的磁碟 contention 風險較低，可避免把壓力集中到 {runner_up_node}。"
        )

    if selected_eval.movement_count < runner_up_eval.movement_count:
        delta = runner_up_eval.movement_count - selected_eval.movement_count
        reasons.append(f"因為不需要多搬 {delta} 台 VM。")

    selected_priority = priorities.get(selected_node, 5)
    runner_up_priority = priorities.get(runner_up_node, 5)
    if (
        selected_priority < runner_up_priority
        and abs(selected_eval.total_score - runner_up_eval.total_score) <= 0.15
    ):
        reasons.append(
            f"在平衡結果接近時，{selected_node} 的節點優先級也比較高。"
        )

    return reasons[:4]


def rebuild_reserved_assignments(
    *,
    session: Session,
    requests: list[VMRequest],
) -> dict[uuid.UUID, CurrentPlacementSelection]:
    """Rebuild node reservations for all approved requests in chronological order."""
    ordered_requests = sorted(
        requests,
        key=lambda item: (
            _normalize_datetime(item.start_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.reviewed_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.created_at) or datetime.min.replace(tzinfo=UTC),
            str(item.id),
        ),
    )
    reserved_so_far: list[VMRequest] = []
    selections: dict[uuid.UUID, CurrentPlacementSelection] = {}

    for request in ordered_requests:
        selection = select_reserved_target_node(
            session=session,
            db_request=request,
            reserved_requests=reserved_so_far,
        )
        if not selection.node or not selection.plan.feasible:
            raise ValueError(
                f"No feasible reservation exists for request {request.id}"
            )
        request.assigned_node = selection.node
        request.placement_strategy_used = selection.strategy
        selections[request.id] = selection
        reserved_so_far.append(request)

    return selections


def rebalance_active_assignments(
    *,
    session: Session,
    requests: list[VMRequest],
) -> dict[uuid.UUID, CurrentPlacementSelection]:
    ordered_requests = sorted(
        requests,
        key=lambda item: (
            _normalize_datetime(item.start_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.reviewed_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.created_at) or datetime.min.replace(tzinfo=UTC),
            str(item.id),
        ),
    )
    working_nodes = _build_rebalance_baseline_nodes(
        session=session,
        requests=ordered_requests,
    )
    strategy = get_placement_strategy(session)
    priorities = get_node_priorities(session)
    tuning = _get_placement_tuning(session=session)

    baseline_nodes = [item.model_copy(deep=True) for item in working_nodes]
    final_assignments = _solve_rebalance_assignments(
        session=session,
        ordered_requests=ordered_requests,
        baseline_nodes=baseline_nodes,
        strategy=strategy,
        priorities=priorities,
        tuning=tuning,
    )

    selections: dict[uuid.UUID, CurrentPlacementSelection] = {}
    for request in ordered_requests:
        placement_request = _to_placement_request(request)
        effective_resource_type, resource_type_reason = advisor_service._decide_resource_type(
            placement_request
        )
        chosen_node = final_assignments.get(request.id)
        if not chosen_node:
            raise ValueError(f"No feasible active rebalance exists for request {request.id}")
        selections[request.id] = CurrentPlacementSelection(
            node=chosen_node,
            strategy=strategy,
            plan=PlacementPlan(
                feasible=True,
                requested_resource_type=placement_request.resource_type,
                effective_resource_type=effective_resource_type,
                resource_type_reason=resource_type_reason,
                assigned_instances=1,
                unassigned_instances=0,
                recommended_node=chosen_node,
                summary=(
                    "Active window rebalance selected the best feasible node "
                    "after greedy placement and local rebalance search."
                ),
                rationale=[],
                warnings=[],
                placements=[],
                candidate_nodes=baseline_nodes,
            ),
        )

    return selections

def compute_node_score_breakdown(
    *,
    session: Session,
    candidate_evals: dict[str, "_AssignmentEvaluation"],
    selected_node: str | None,
    priorities: dict[str, int] | None = None,
) -> list[NodeScoreBreakdown]:
    if not candidate_evals:
        return []
    tuning = _get_placement_tuning(session=session)
    priorities = priorities or get_node_priorities(session)
    breakdowns: list[NodeScoreBreakdown] = []
    for node_name, evaluation in sorted(candidate_evals.items()):
        node_score = (evaluation.node_scores or {}).get(node_name, 0.0)
        storage_pen = (evaluation.storage_penalties or {}).get(node_name, 0.0)
        breakdowns.append(NodeScoreBreakdown(
            node=node_name,
            balance_score=round(node_score, 4),
            cpu_share=round(evaluation.objective[0], 4) if evaluation.feasible else 0.0,
            memory_share=0.0,
            disk_share=0.0,
            peak_penalty=0.0,
            loadavg_penalty=0.0,
            storage_penalty=round(storage_pen * tuning.disk_penalty_weight, 4),
            migration_cost=round(evaluation.movement_count * tuning.migration_cost, 4),
            priority=priorities.get(node_name, 5),
            is_selected=node_name == selected_node,
            reason=(
                "最佳平衡方案" if node_name == selected_node
                else ("可行但非最佳" if evaluation.feasible else "不可行")
            ),
        ))
    breakdowns.sort(key=lambda b: (not b.is_selected, b.balance_score, b.priority))
    return breakdowns


def get_preview_node_scores(
    *,
    session: Session,
    db_request: VMRequest,
    reserved_requests: list[VMRequest] | None = None,
) -> list[NodeScoreBreakdown]:
    start_at, end_at = _request_window(db_request)
    if not start_at or not end_at:
        return []

    request = _to_placement_request(db_request)
    effective_resource_type, _ = advisor_service._decide_resource_type(request)

    nodes, resources = advisor_service._load_cluster_state()
    cpu_overcommit_ratio, disk_overcommit_ratio = get_overcommit_ratios(session)
    baseline_capacities = advisor_service._build_node_capacities(
        nodes=nodes,
        resources=resources,
        cpu_overcommit_ratio=cpu_overcommit_ratio,
        disk_overcommit_ratio=disk_overcommit_ratio,
    )

    if reserved_requests is None:
        reserved_requests = vm_request_repo.get_approved_vm_requests_overlapping_window(
            session=session,
            window_start=start_at,
            window_end=end_at,
        )

    checkpoints = [start_at] + [
        checkpoint
        for checkpoint in _hour_window_iter(start_at, end_at)
        if checkpoint != start_at
    ]

    feasible_nodes = {item.node for item in baseline_capacities}
    for checkpoint in checkpoints:
        adjusted = _apply_reserved_requests_to_capacities(
            baseline_capacities=baseline_capacities,
            reserved_requests=reserved_requests,
            at_time=checkpoint,
        )
        hour_feasible = {
            item.node for item in adjusted
            if advisor_service._can_fit(
                item,
                cores=advisor_service._effective_cpu_cores(request, effective_resource_type),
                memory_bytes=advisor_service._effective_memory_bytes(request, effective_resource_type),
                disk_bytes=request.disk_gb * GIB,
                gpu_required=request.gpu_required,
            )
        }
        feasible_nodes &= hour_feasible
        if not feasible_nodes:
            break

    if not feasible_nodes:
        return []

    overlapping_start_requests = [
        item for item in reserved_requests
        if (w := _request_window(item))[0] is not None
        and w[1] is not None
        and w[0] <= start_at < w[1]
    ]
    preview_request = _build_preview_vm_request(
        request=request, start_at=start_at, end_at=end_at,
    )
    preview_cohort = overlapping_start_requests + [preview_request]
    preview_ordered = sorted(
        preview_cohort,
        key=lambda item: (
            _normalize_datetime(item.start_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.reviewed_at) or datetime.min.replace(tzinfo=UTC),
            _normalize_datetime(item.created_at) or datetime.min.replace(tzinfo=UTC),
            str(item.id),
        ),
    )
    preview_baseline = _build_rebalance_baseline_nodes(
        session=session, requests=preview_ordered,
    )
    preview_baseline = [
        item.model_copy(deep=True) for item in preview_baseline
        if item.node in feasible_nodes
    ]

    priorities = get_node_priorities(session)
    strategy = get_placement_strategy(session)
    tuning = _get_placement_tuning(session=session)

    candidate_evals: dict[str, _AssignmentEvaluation] = {}
    best_node: str | None = None
    best_obj = None
    for candidate_node in sorted(feasible_nodes):
        try:
            assignments = _solve_rebalance_assignments(
                session=session,
                ordered_requests=preview_ordered,
                baseline_nodes=preview_baseline,
                strategy=strategy,
                priorities=priorities,
                tuning=tuning,
                fixed_assignments={preview_request.id: candidate_node},
            )
            evaluation = _evaluate_active_assignment_map(
                session=session,
                ordered_requests=preview_ordered,
                baseline_nodes=preview_baseline,
                assignments=assignments,
                priorities=priorities,
                tuning=tuning,
            )
        except ValueError:
            continue
        if not evaluation.feasible:
            continue
        candidate_evals[candidate_node] = evaluation
        if best_obj is None or evaluation.objective < best_obj:
            best_obj = evaluation.objective
            best_node = candidate_node

    return compute_node_score_breakdown(
        session=session,
        candidate_evals=candidate_evals,
        selected_node=best_node,
        priorities=priorities,
    )


def get_placement_strategy(session: Session) -> str:
    return placement_policy.get_placement_strategy(session)


def get_overcommit_ratios(session: Session) -> tuple[float, float]:
    return placement_policy.get_overcommit_ratios(session)


def get_node_priorities(session: Session) -> dict[str, int]:
    return placement_policy.get_node_priorities(session)


def select_best_storage_name(
    *,
    session: Session,
    node_name: str,
    resource_type: str,
    disk_gb: int,
    fallback_storage: str | None = None,
) -> str | None:
    storage_pools_by_node, has_managed_storage = _build_storage_pool_state(
        session=session,
        node_names=[node_name],
    )
    if not has_managed_storage:
        return fallback_storage

    _, disk_overcommit_ratio = get_overcommit_ratios(session)
    selection = _select_best_storage_for_request(
        storage_pools=storage_pools_by_node.get(node_name, []),
        resource_type=resource_type,
        disk_gb=disk_gb,
        disk_overcommit_ratio=disk_overcommit_ratio,
        tuning=_get_placement_tuning(session=session),
    )
    if selection is None:
        return None
    return selection.pool.storage


def _placement_sort_key(
    node: NodeCapacity,
    *,
    placements: dict[str, int],
    priorities: dict[str, int],
    strategy: str,
    cores: float,
    memory_bytes: int,
    disk_bytes: int,
    storage_selection: _StorageSelection | None = None,
    tuning: _PlacementTuning | None = None,
    current_node: str | None = None,
) -> tuple:
    tuning = tuning or _PlacementTuning(
        migration_cost=0.15,
        peak_cpu_margin=1.1,
        peak_memory_margin=1.05,
        loadavg_warn_per_core=0.8,
        loadavg_max_per_core=1.5,
        loadavg_penalty_weight=0.9,
        disk_contention_warn_share=0.7,
        disk_contention_high_share=0.9,
        disk_penalty_weight=0.75,
        search_max_relocations=2,
        search_depth=3,
    )
    projected_cpu_share = _projected_share(
        used=max(node.total_cpu_cores - node.allocatable_cpu_cores, 0.0) + cores,
        total=max(node.total_cpu_cores, 1.0),
    )
    projected_memory_share = _projected_share(
        used=max(node.total_memory_bytes - node.allocatable_memory_bytes, 0) + memory_bytes,
        total=max(node.total_memory_bytes, 1),
    )
    projected_disk_share = _projected_share(
        used=max(node.total_disk_bytes - node.allocatable_disk_bytes, 0) + disk_bytes,
        total=max(node.total_disk_bytes, 1),
    )
    w_cpu = tuning.resource_weight_cpu
    w_mem = tuning.resource_weight_memory
    w_disk = tuning.resource_weight_disk
    weighted_shares = [
        projected_cpu_share * w_cpu,
        projected_memory_share * w_mem,
        projected_disk_share * w_disk,
    ]
    dominant_share = max(weighted_shares)
    weight_sum = w_cpu + w_mem + w_disk
    average_share = sum(weighted_shares) / max(weight_sum, 0.01)
    peak_penalty = _peak_penalty(
        projected_cpu_share=_projected_share(
            used=max(node.total_cpu_cores - node.allocatable_cpu_cores, 0.0)
            + (cores * tuning.peak_cpu_margin),
            total=max(node.total_cpu_cores, 1.0),
        ),
        projected_memory_share=_projected_share(
            used=max(node.total_memory_bytes - node.allocatable_memory_bytes, 0)
            + int(memory_bytes * tuning.peak_memory_margin),
            total=max(node.total_memory_bytes, 1),
        ),
        tuning=tuning,
    )
    loadavg_penalty = _loadavg_penalty(
        _reference_loadavg_per_core(node),
        tuning=tuning,
    )
    cpu_contention = _cpu_contention_penalty(projected_cpu_share, tuning=tuning)
    cpu_contention_score = cpu_contention * tuning.cpu_contention_weight

    memory_overflow_penalty = (
        tuning.memory_overflow_weight
        if projected_memory_share > 1.0 + 1e-9
        else 0.0
    )
    migration_penalty = (
        tuning.migration_cost
        if current_node and current_node != node.node
        else 0.0
    )
    disk_penalty = (
        storage_selection.contention_penalty * tuning.disk_penalty_weight
        if storage_selection is not None
        else 0.0
    )
    total_score = (
        dominant_share
        + peak_penalty
        + cpu_contention_score
        + memory_overflow_penalty
        + (loadavg_penalty * tuning.loadavg_penalty_weight)
        + migration_penalty
        + disk_penalty
    )
    placement_count = placements.get(node.node, 0)
    storage_speed_rank = (
        storage_selection.speed_rank if storage_selection is not None else 99
    )
    storage_user_priority = (
        storage_selection.user_priority if storage_selection is not None else 99
    )
    storage_projected_share = (
        storage_selection.projected_share if storage_selection is not None else 1.0
    )

    return (
        total_score,
        dominant_share,
        average_share,
        priorities.get(node.node, 5),
        placement_count,
        projected_cpu_share,
        storage_speed_rank,
        storage_user_priority,
        storage_projected_share,
        node.node,
    )


def _normalize_strategy(strategy: str | None) -> str:
    return placement_policy.normalize_strategy(strategy)


def _to_placement_request(db_request: VMRequest) -> PlacementRequest:
    disk_gb = (
        int(db_request.disk_size or 0)
        if db_request.resource_type == "vm"
        else int(db_request.rootfs_size or 0)
    )
    if disk_gb <= 0:
        disk_gb = 20 if db_request.resource_type == "vm" else 8

    return PlacementRequest(
        resource_type=db_request.resource_type,
        cpu_cores=int(db_request.cores or 1),
        memory_mb=int(db_request.memory or 512),
        disk_gb=disk_gb,
        instance_count=1,
        gpu_required=0,
    )
