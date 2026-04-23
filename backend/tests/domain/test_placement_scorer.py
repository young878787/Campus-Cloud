"""Tests for pure scoring helpers in app.domain.placement.scorer.

These functions are deterministic and depend only on numeric inputs +
PlacementTuning, so they can be exhaustively tested without any DB or
Proxmox calls.
"""

from __future__ import annotations

import pytest

from app.domain.placement.models import PlacementTuning
from app.domain.placement.scorer import (
    cpu_contention_penalty,
    linear_penalty,
    loadavg_penalty,
    peak_penalty,
    projected_share,
    storage_contention_penalty,
)


def _tuning(**overrides) -> PlacementTuning:
    defaults = dict(
        migration_cost=0.5,
        peak_cpu_margin=0.1,
        peak_memory_margin=0.1,
        loadavg_warn_per_core=1.0,
        loadavg_max_per_core=2.0,
        loadavg_penalty_weight=1.0,
        disk_contention_warn_share=0.7,
        disk_contention_high_share=0.9,
        disk_penalty_weight=1.0,
        search_max_relocations=10,
        search_depth=5,
        cpu_peak_warn_share=0.7,
        cpu_peak_high_share=0.9,
        memory_peak_warn_share=0.7,
        memory_peak_high_share=0.9,
    )
    defaults.update(overrides)
    return PlacementTuning(**defaults)


# ─── projected_share ────────────────────────────────────────────────────────


def test_projected_share_zero_total_uses_default_denominator() -> None:
    # When total is 0, denominator falls back to 1.0 (current implementation).
    assert projected_share(used=10, total=0) == 10.0
    # used=0, total=0 → 0/1.0 = 0.0
    assert projected_share(used=0, total=0) == 0.0


def test_projected_share_normal_division() -> None:
    assert projected_share(used=25, total=100) == 0.25


def test_projected_share_used_exceeds_total_can_exceed_1() -> None:
    # No clamping here — overcommit is reported as >1 to caller.
    assert projected_share(used=150, total=100) == 1.5


# ─── linear_penalty ─────────────────────────────────────────────────────────


def test_linear_penalty_below_low_returns_zero() -> None:
    assert linear_penalty(0.5, low=0.7, high=0.9) == 0.0


def test_linear_penalty_above_high_returns_one() -> None:
    assert linear_penalty(0.95, low=0.7, high=0.9) == 1.0


def test_linear_penalty_midpoint_is_half() -> None:
    assert linear_penalty(0.8, low=0.7, high=0.9) == pytest.approx(0.5)


def test_linear_penalty_at_low_is_zero_and_at_high_is_one() -> None:
    assert linear_penalty(0.7, low=0.7, high=0.9) == 0.0
    assert linear_penalty(0.9, low=0.7, high=0.9) == 1.0


# ─── peak_penalty ───────────────────────────────────────────────────────────


def test_peak_penalty_takes_max_of_cpu_and_memory() -> None:
    tuning = _tuning(
        cpu_peak_warn_share=0.7,
        cpu_peak_high_share=0.9,
        memory_peak_warn_share=0.7,
        memory_peak_high_share=0.9,
    )
    # CPU mid (0.8 → 0.5), memory low (0.5 → 0.0)
    assert peak_penalty(
        projected_cpu_share=0.8,
        projected_memory_share=0.5,
        tuning=tuning,
    ) == pytest.approx(0.5)

    # Memory dominates
    assert peak_penalty(
        projected_cpu_share=0.5,
        projected_memory_share=0.95,
        tuning=tuning,
    ) == 1.0


# ─── cpu_contention_penalty ─────────────────────────────────────────────────


def test_cpu_contention_below_warn_is_zero() -> None:
    assert cpu_contention_penalty(0.6, tuning=_tuning()) == 0.0


def test_cpu_contention_at_high_is_one() -> None:
    assert cpu_contention_penalty(0.95, tuning=_tuning()) == 1.0


# ─── loadavg_penalty ────────────────────────────────────────────────────────


def test_loadavg_penalty_none_returns_zero() -> None:
    assert loadavg_penalty(None, tuning=_tuning()) == 0.0


def test_loadavg_penalty_below_warn_is_zero() -> None:
    assert loadavg_penalty(0.5, tuning=_tuning()) == 0.0


def test_loadavg_penalty_above_max_is_one() -> None:
    assert loadavg_penalty(3.0, tuning=_tuning()) == 1.0


def test_loadavg_penalty_midpoint_is_half() -> None:
    # warn=1.0, max=2.0 → midpoint 1.5 → 0.5
    assert loadavg_penalty(1.5, tuning=_tuning()) == 0.5


# ─── storage_contention_penalty ─────────────────────────────────────────────


def test_storage_contention_overcommit_adds_half() -> None:
    tuning = _tuning()
    no_oc = storage_contention_penalty(
        projected_share=0.5,
        placed_count=0,
        overcommit_placed_count=0,
        tuning=tuning,
        overcommit=False,
    )
    with_oc = storage_contention_penalty(
        projected_share=0.5,
        placed_count=0,
        overcommit_placed_count=0,
        tuning=tuning,
        overcommit=True,
    )
    assert with_oc - no_oc == 0.5


def test_storage_contention_placed_count_capped() -> None:
    tuning = _tuning()
    huge = storage_contention_penalty(
        projected_share=0.0,
        placed_count=1000,  # >> 6, should saturate at 0.35
        overcommit_placed_count=0,
        tuning=tuning,
        overcommit=False,
    )
    assert huge == 0.35
