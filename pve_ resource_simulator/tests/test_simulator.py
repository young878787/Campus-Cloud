from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import ServerInput, SimulationRequest, VMTemplate
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

    assert result.hours[8].placements[0].server_name == "pve-b"
    assert result.hours[8].summary.recommendation_target == "pve-b"


def test_rebalance_can_free_space_for_large_vm_in_active_hour() -> None:
    request = SimulationRequest(
        servers=[
            ServerInput(name="pve-a", cpu_cores=24, memory_gb=96, disk_gb=1200),
            ServerInput(name="pve-b", cpu_cores=16, memory_gb=64, disk_gb=900),
            ServerInput(name="pve-c", cpu_cores=32, memory_gb=128, disk_gb=1600),
        ],
        vm_templates=[
            VMTemplate(
                id="vm-01",
                name="vm-01",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=40,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-02",
                name="vm-02",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=40,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-03",
                name="vm-03",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=40,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-04",
                name="vm-04",
                cpu_cores=2,
                memory_gb=4,
                disk_gb=40,
                active_hours=[12],
            ),
            VMTemplate(
                id="vm-05",
                name="vm-05",
                cpu_cores=30,
                memory_gb=4,
                disk_gb=40,
                active_hours=[12],
            ),
        ],
        allow_rebalance=True,
    )

    result = run_simulation(request)

    hour_12 = result.hours[12]
    assert hour_12.summary.total_placements == 5
    assert not hour_12.summary.failed_vm_names
    pve_c = next(server for server in hour_12.states[-1].servers if server.name == "pve-c")
    assert any(item.name == "vm-05" for item in pve_c.vm_stack)
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
