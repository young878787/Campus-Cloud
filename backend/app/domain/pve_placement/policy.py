from __future__ import annotations

from sqlmodel import Session

from app.domain.pve_placement.constants import DEFAULT_PLACEMENT_STRATEGY
from app.domain.pve_placement.models import (
    DEFAULT_CPU_PEAK_HIGH_SHARE,
    DEFAULT_CPU_PEAK_WARN_SHARE,
    DEFAULT_RAM_PEAK_HIGH_SHARE,
    DEFAULT_RAM_PEAK_WARN_SHARE,
    PlacementTuning,
)
from app.repositories import proxmox_config as proxmox_config_repo
from app.repositories import proxmox_node as proxmox_node_repo


def get_placement_tuning(*, session: Session) -> PlacementTuning:
    config = proxmox_config_repo.get_proxmox_config(session)
    if config is None:
        return PlacementTuning(
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
    return PlacementTuning(
        migration_cost=max(float(config.rebalance_migration_cost or 0.15), 0.0),
        peak_cpu_margin=max(float(config.rebalance_peak_cpu_margin or 1.1), 1.0),
        peak_memory_margin=max(float(config.rebalance_peak_memory_margin or 1.05), 1.0),
        loadavg_warn_per_core=max(float(config.rebalance_loadavg_warn_per_core or 0.8), 0.0),
        loadavg_max_per_core=max(float(config.rebalance_loadavg_max_per_core or 1.5), 0.01),
        loadavg_penalty_weight=max(float(config.rebalance_loadavg_penalty_weight or 0.9), 0.0),
        disk_contention_warn_share=max(
            float(config.rebalance_disk_contention_warn_share or 0.7),
            0.0,
        ),
        disk_contention_high_share=max(
            float(config.rebalance_disk_contention_high_share or 0.9),
            0.01,
        ),
        disk_penalty_weight=max(float(config.rebalance_disk_penalty_weight or 0.75), 0.0),
        search_max_relocations=max(int(config.rebalance_search_max_relocations or 2), 0),
        search_depth=max(int(config.rebalance_search_depth or 3), 0),
        cpu_peak_warn_share=max(
            float(config.rebalance_cpu_peak_warn_share or DEFAULT_CPU_PEAK_WARN_SHARE),
            0.0,
        ),
        cpu_peak_high_share=max(
            float(config.rebalance_cpu_peak_high_share or DEFAULT_CPU_PEAK_HIGH_SHARE),
            0.01,
        ),
        memory_peak_warn_share=max(
            float(config.rebalance_memory_peak_warn_share or DEFAULT_RAM_PEAK_WARN_SHARE),
            0.0,
        ),
        memory_peak_high_share=max(
            float(config.rebalance_memory_peak_high_share or DEFAULT_RAM_PEAK_HIGH_SHARE),
            0.01,
        ),
        resource_weight_cpu=max(float(config.rebalance_resource_weight_cpu or 1.0), 0.0),
        resource_weight_memory=max(float(config.rebalance_resource_weight_memory or 1.0), 0.0),
        resource_weight_disk=max(float(config.rebalance_resource_weight_disk or 1.0), 0.0),
        lxc_live_migration_enabled=bool(config.migration_lxc_live_enabled),
    )


def get_overcommit_ratios(session: Session) -> tuple[float, float]:
    config = proxmox_config_repo.get_proxmox_config(session)
    if not config:
        return 1.0, 1.0

    return (
        max(float(config.cpu_overcommit_ratio or 1.0), 1.0),
        max(float(config.disk_overcommit_ratio or 1.0), 1.0),
    )


def get_node_priorities(session: Session) -> dict[str, int]:
    return {
        item.name: int(item.priority)
        for item in proxmox_node_repo.get_all_nodes(session)
    }


def get_placement_strategy(session: Session) -> str:
    config = proxmox_config_repo.get_proxmox_config(session)
    if not config:
        return DEFAULT_PLACEMENT_STRATEGY
    return normalize_strategy(config.placement_strategy)


def normalize_strategy(strategy: str | None) -> str:
    del strategy
    return DEFAULT_PLACEMENT_STRATEGY
