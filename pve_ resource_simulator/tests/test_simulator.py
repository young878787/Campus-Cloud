from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas import HistoricalProfile, HourlyUsagePoint, ServerInput, SimulationRequest, VMTemplate
from app.services import simulator_service
from app.services.simulator_service import run_simulation


client = TestClient(app)


def test_default_scenario_starts_empty() -> None:
    response = client.get("/api/v1/scenario/default")
    payload = response.json()

    assert response.status_code == 200
    assert len(payload["servers"]) == 3
    assert payload["vm_templates"] == []


def test_vm_template_defaults_to_all_day_hours() -> None:
    template = VMTemplate(
        id="vm-1",
        name="VM 1",
        cpu_cores=2,
        memory_gb=4,
        disk_gb=20,
    )

    assert template.active_hours == list(range(24))


def test_vm_template_rejects_non_contiguous_hours() -> None:
    try:
        VMTemplate(
            id="vm-gap",
            name="VM Gap",
            cpu_cores=2,
            memory_gb=4,
            disk_gb=20,
            active_hours=[9, 11],
        )
    except ValidationError as exc:
        assert "continuous range" in str(exc)
    else:
        raise AssertionError("non-contiguous active_hours should be rejected")


def test_hourly_reservation_only_appears_in_selected_hours() -> None:
    request = SimulationRequest(
        servers=[
            ServerInput(name="pve-a", cpu_cores=8, memory_gb=16, disk_gb=200),
            ServerInput(name="pve-b", cpu_cores=8, memory_gb=16, disk_gb=200),
        ],
        vm_templates=[
            VMTemplate(
                id="vm-morning",
                name="Morning VM",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[9, 10],
            )
        ],
    )

    result = run_simulation(request)

    hour_9 = result.hours[9]
    hour_11 = result.hours[11]
    assert hour_9.summary.total_placements == 1
    assert hour_9.active_vm_names == ["Morning VM"]
    assert hour_11.summary.total_placements == 0
    assert hour_11.active_vm_names == []


def test_dominant_share_chooses_lower_post_share_server() -> None:
    request = SimulationRequest(
        servers=[
            ServerInput(
                name="pve-a",
                cpu_cores=16,
                memory_gb=64,
                disk_gb=800,
                gpu_count=0,
                cpu_used=8,
                memory_used_gb=16,
                disk_used_gb=200,
            ),
            ServerInput(
                name="pve-b",
                cpu_cores=16,
                memory_gb=64,
                disk_gb=800,
                gpu_count=0,
                cpu_used=4,
                memory_used_gb=28,
                disk_used_gb=200,
            ),
        ],
        vm_templates=[
            VMTemplate(
                id="general",
                name="General",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=50,
                active_hours=[8],
            )
        ],
        selected_vm_template_id="general",
    )

    result = run_simulation(request)

    assert result.hours[8].placements[0].server_name == "pve-a"
    assert result.hours[8].summary.recommendation_target == "pve-a"


def test_local_rebalance_can_free_space_for_large_vm_in_active_hour() -> None:
    request = SimulationRequest(
        servers=[
            ServerInput(name="pve-a", cpu_cores=8, memory_gb=12, disk_gb=200),
            ServerInput(name="pve-b", cpu_cores=8, memory_gb=12, disk_gb=200),
            ServerInput(name="pve-c", cpu_cores=8, memory_gb=12, disk_gb=200),
        ],
        vm_templates=[
            VMTemplate(
                id="vm-01",
                name="vm-01",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-02",
                name="vm-02",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-03",
                name="vm-03",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-04",
                name="vm-04",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-05",
                name="vm-05",
                cpu_cores=2,
                memory_gb=8,
                disk_gb=20,
                active_hours=[12],
            ),
        ],
        allow_rebalance=True,
    )

    result = run_simulation(request)

    hour_12 = result.hours[12]
    assert hour_12.summary.total_placements == 5
    assert not hour_12.summary.failed_vm_names
    assert any(item.vm_name == "vm-05" for item in hour_12.placements)
    assert any("Auto-rebalanced" in state.latest_placement.reason for state in hour_12.states if state.latest_placement)


def test_daily_summary_tracks_reservation_counts() -> None:
    request = SimulationRequest(
        servers=[ServerInput(name="pve-a", cpu_cores=8, memory_gb=16, disk_gb=200)],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[8, 9, 10],
            ),
            VMTemplate(
                id="vm-2",
                name="VM 2",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
    )

    result = run_simulation(request)

    assert result.summary.reserved_vm_count == 2
    assert result.summary.reservation_slot_count == 4
    assert result.summary.active_hours == [8, 9, 10]
    assert result.summary.reservations_by_hour["9"] == 2
    assert result.summary.peak_hour == 9


def test_simulate_endpoint_returns_hourly_timeline() -> None:
    response = client.get("/api/v1/scenario/default")
    scenario = response.json()
    scenario["vm_templates"] = [
        {
            "id": "vm-1",
            "name": "VM 1",
            "cpu_cores": 2,
            "memory_gb": 4,
            "disk_gb": 20,
            "gpu_count": 0,
            "active_hours": [13, 14],
            "enabled": True,
        }
    ]

    simulate_response = client.post(
        "/api/v1/simulate",
        json={
            "servers": scenario["servers"],
            "vm_templates": scenario["vm_templates"],
        },
    )

    assert simulate_response.status_code == 200
    payload = simulate_response.json()
    assert len(payload["hours"]) == 24
    assert payload["hours"][13]["summary"]["requested_vm_count"] == 1
    assert payload["summary"]["active_hours"] == [13, 14]


def test_historical_profile_reduces_effective_cpu_and_memory_when_available() -> None:
    request = SimulationRequest(
        servers=[ServerInput(name="pve-a", cpu_cores=3, memory_gb=4, disk_gb=200)],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=2,
                disk_gb=20,
                active_hours=[9],
            ),
            VMTemplate(
                id="vm-2",
                name="VM 2",
                cpu_cores=2,
                memory_gb=2,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
        historical_profiles=[
            HistoricalProfile(
                type_label="2 vCPU / 2 GiB",
                configured_cpu_cores=2,
                configured_memory_gb=2,
                guest_count=3,
                average_cpu_ratio=0.35,
                average_memory_ratio=0.5,
                peak_cpu_ratio=0.8,
                peak_memory_ratio=0.9,
                hourly=[
                    HourlyUsagePoint(hour=9, label="09:00", sample_count=3, cpu_ratio=0.35, memory_ratio=0.5),
                ],
            )
        ],
    )

    result = run_simulation(request)

    assert result.hours[9].summary.total_placements == 2


def test_trend_ratio_participates_in_effective_baseline() -> None:
    request = SimulationRequest(
        servers=[ServerInput(name="pve-a", cpu_cores=8, memory_gb=16, disk_gb=200)],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
        historical_profiles=[
            HistoricalProfile(
                type_label="2 vCPU / 4 GiB",
                configured_cpu_cores=2,
                configured_memory_gb=4,
                guest_count=3,
                average_cpu_ratio=0.35,
                average_memory_ratio=0.4,
                trend_cpu_ratio=0.6,
                trend_memory_ratio=0.7,
                peak_cpu_ratio=0.8,
                peak_memory_ratio=0.9,
                hourly=[],
            )
        ],
    )

    result = run_simulation(request)
    calculation = result.hours[9].calculations[0]

    assert calculation.effective_cpu_cores == pytest.approx(1.68)
    assert calculation.effective_memory_gb == pytest.approx(3.22)


def test_cpu_overcommit_allows_placement_beyond_physical_core_count() -> None:
    request = SimulationRequest(
        servers=[ServerInput(name="pve-a", cpu_cores=4, memory_gb=32, disk_gb=200)],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=3,
                memory_gb=2,
                disk_gb=20,
                active_hours=[9],
            ),
            VMTemplate(
                id="vm-2",
                name="VM 2",
                cpu_cores=3,
                memory_gb=2,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
    )

    result = run_simulation(request)

    assert result.hours[9].summary.total_placements == 2
    assert not result.hours[9].summary.failed_vm_names


def test_high_loadavg_penalty_prefers_less_busy_host() -> None:
    request = SimulationRequest(
        servers=[
            ServerInput(
                name="pve-a",
                cpu_cores=8,
                memory_gb=16,
                disk_gb=200,
                current_loadavg_1=12.0,
            ),
            ServerInput(
                name="pve-b",
                cpu_cores=8,
                memory_gb=16,
                disk_gb=200,
                current_loadavg_1=1.0,
            ),
        ],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
        selected_vm_template_id="vm-1",
    )

    result = run_simulation(request)

    assert result.hours[9].placements[0].server_name == "pve-b"
    assert result.hours[9].summary.recommendation_target == "pve-b"


def test_high_loadavg_adds_warning_but_does_not_block_placement() -> None:
    request = SimulationRequest(
        servers=[
            ServerInput(
                name="pve-a",
                cpu_cores=8,
                memory_gb=16,
                disk_gb=200,
                current_loadavg_1=12.0,
            ),
        ],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
        selected_vm_template_id="vm-1",
    )

    result = run_simulation(request)

    assert result.hours[9].summary.total_placements == 1
    assert "Host loadavg is elevated" in result.hours[9].placements[0].reason
    assert "Loadavg penalty is active for" in result.hours[9].summary.narrative


def test_ram_safety_buffer_blocks_placement_before_physical_ram_is_full() -> None:
    request = SimulationRequest(
        servers=[ServerInput(name="pve-a", cpu_cores=8, memory_gb=16, disk_gb=200)],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=15,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
    )

    result = run_simulation(request)

    assert result.hours[9].summary.total_placements == 0
    assert result.hours[9].summary.failed_vm_names == ["VM 1"]


def test_peak_guard_marks_high_risk_when_peak_pushes_node_near_limit() -> None:
    request = SimulationRequest(
        servers=[
            ServerInput(
                name="pve-a",
                cpu_cores=4,
                memory_gb=4,
                disk_gb=200,
                cpu_used=1.8,
                memory_used_gb=1.6,
            )
        ],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=2,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
        historical_profiles=[
            HistoricalProfile(
                type_label="2 vCPU / 2 GiB",
                configured_cpu_cores=2,
                configured_memory_gb=2,
                guest_count=3,
                average_cpu_ratio=0.35,
                average_memory_ratio=0.5,
                peak_cpu_ratio=0.85,
                peak_memory_ratio=0.9,
                hourly=[
                    HourlyUsagePoint(hour=9, label="09:00", sample_count=3, cpu_ratio=0.35, memory_ratio=0.5),
                ],
            )
        ],
    )

    result = run_simulation(request)
    calculation = result.hours[9].calculations[0]

    assert calculation.placement_status == "placed"
    assert calculation.peak_cpu_cores == pytest.approx(1.87)
    assert calculation.peak_memory_gb == pytest.approx(1.89)
    assert calculation.peak_risk == "high"


def test_hourly_peak_ratio_overrides_profile_peak_for_same_hour() -> None:
    request = SimulationRequest(
        servers=[ServerInput(name="pve-a", cpu_cores=8, memory_gb=8, disk_gb=200)],
        vm_templates=[
            VMTemplate(
                id="vm-1",
                name="VM 1",
                cpu_cores=2,
                memory_gb=2,
                disk_gb=20,
                active_hours=[9],
            ),
        ],
        historical_profiles=[
            HistoricalProfile(
                type_label="2 vCPU / 2 GiB",
                configured_cpu_cores=2,
                configured_memory_gb=2,
                guest_count=3,
                average_cpu_ratio=0.35,
                average_memory_ratio=0.5,
                peak_cpu_ratio=0.95,
                peak_memory_ratio=0.95,
                hourly=[
                    HourlyUsagePoint(
                        hour=9,
                        label="09:00",
                        sample_count=3,
                        cpu_ratio=0.35,
                        memory_ratio=0.5,
                        peak_cpu_ratio=0.5,
                        peak_memory_ratio=0.6,
                    ),
                ],
            )
        ],
    )

    result = run_simulation(request)
    calculation = result.hours[9].calculations[0]

    assert calculation.peak_cpu_cores == pytest.approx(1.1)
    assert calculation.peak_memory_gb == pytest.approx(1.26)


def test_build_live_scenario_uses_online_nodes_and_profiles(monkeypatch) -> None:
    from app.schemas import (
        ClusterUsageSummary,
        GuestTypeUsageSummary,
        HourlyUsagePoint,
        NodeUsageSummary,
        ProxmoxMonthlyAnalyticsResponse,
    )

    async def fake_fetch_monthly_analytics():
        return ProxmoxMonthlyAnalyticsResponse(
            host="192.168.100.2",
            timezone="Asia/Taipei",
            generated_at="2026-03-30T00:00:00+08:00",
            month_label="2026-03",
            cluster=ClusterUsageSummary(
                hourly=[
                    HourlyUsagePoint(hour=8, label="08:00", cpu_ratio=0.2, memory_ratio=0.4, disk_ratio=0.1),
                    HourlyUsagePoint(hour=9, label="09:00", cpu_ratio=0.3, memory_ratio=0.8, disk_ratio=0.1),
                    HourlyUsagePoint(hour=10, label="10:00", cpu_ratio=0.1, memory_ratio=0.5, disk_ratio=0.1),
                ]
            ),
            nodes=[
                NodeUsageSummary(
                    name="pve",
                    status="online",
                    total_cpu_cores=30,
                    total_memory_gb=64,
                    total_disk_gb=500,
                    current_cpu_ratio=0.5,
                    current_memory_ratio=0.25,
                    current_disk_ratio=0.1,
                    current_loadavg=[6.0, 5.0, 4.0],
                    average_loadavg_1=4.5,
                ),
                NodeUsageSummary(
                    name="pve2",
                    status="unreachable",
                    fetch_error="HTTP 595: No route to host",
                ),
            ],
            guest_types=[
                GuestTypeUsageSummary(
                    type_label="2 vCPU / 2 GiB",
                    configured_cpu_cores=2,
                    configured_memory_gb=2,
                    guest_count=2,
                    average_cpu_ratio=0.3,
                    average_memory_ratio=0.5,
                )
            ],
        )

    monkeypatch.setattr(
        simulator_service.proxmox_analytics_service,
        "fetch_monthly_analytics",
        fake_fetch_monthly_analytics,
    )

    scenario = simulator_service.build_live_scenario()
    import asyncio
    scenario = asyncio.run(scenario)

    assert scenario.source == "live"
    assert len(scenario.servers) == 1
    assert scenario.servers[0].name == "pve"
    assert scenario.servers[0].cpu_used == 15
    assert len(scenario.historical_profiles) == 1
    assert scenario.historical_peak_hours == [9]
    assert scenario.historical_hourly_peaks["8"] == pytest.approx(0.4)
    assert scenario.historical_hourly_peaks["9"] == pytest.approx(0.8)
    assert scenario.servers[0].current_loadavg_1 == pytest.approx(6.0)
    assert scenario.servers[0].average_loadavg_1 == pytest.approx(4.5)
