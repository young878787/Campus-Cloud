from __future__ import annotations

import importlib

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.ai.pve_advisor.recommendation_service import (
    _build_ai_plan_from_decision,
    _build_rule_based_plan,
    _decide_resource_type,
)
from app.ai.pve_advisor.schemas import (
    NodeCapacity,
    PlacementAdvisorResponse,
    PlacementRequest,
)
from app.core.config import settings

advisor_router_module = importlib.import_module("app.api.routes.ai_pve_advisor")


def test_placement_request_accepts_minimal_fields() -> None:
    request = PlacementRequest.model_validate(
        {
            "container_type": "lxc",
            "cpu": 2,
            "memory_gb": 4,
            "disk": 30,
            "count": 3,
        }
    )

    assert request.resource_type == "lxc"
    assert request.cpu_cores == 2
    assert request.memory_mb == 4096
    assert request.disk_gb == 30
    assert request.instance_count == 3


def test_ai_plan_is_used_when_valid() -> None:
    request = PlacementRequest(
        resource_type="lxc",
        cpu_cores=2,
        memory_mb=2048,
        disk_gb=20,
        instance_count=2,
    )
    node_capacities = [
        NodeCapacity(
            node="pve-a",
            status="online",
            candidate=True,
            running_resources=4,
            guest_soft_limit=16,
            cpu_ratio=0.2,
            memory_ratio=0.2,
            disk_ratio=0.2,
            total_cpu_cores=16,
            allocatable_cpu_cores=10,
            total_memory_bytes=64 * 1024**3,
            allocatable_memory_bytes=40 * 1024**3,
            total_disk_bytes=1000 * 1024**3,
            allocatable_disk_bytes=600 * 1024**3,
        ),
        NodeCapacity(
            node="pve-b",
            status="online",
            candidate=True,
            running_resources=4,
            guest_soft_limit=16,
            cpu_ratio=0.1,
            memory_ratio=0.1,
            disk_ratio=0.1,
            total_cpu_cores=16,
            allocatable_cpu_cores=12,
            total_memory_bytes=64 * 1024**3,
            allocatable_memory_bytes=48 * 1024**3,
            total_disk_bytes=1000 * 1024**3,
            allocatable_disk_bytes=700 * 1024**3,
        ),
    ]
    resource_type, reason = _decide_resource_type(request)
    fallback_plan = _build_rule_based_plan(
        request=request,
        node_capacities=node_capacities,
        effective_resource_type=resource_type,
        resource_type_reason=reason,
    )

    ai_plan = _build_ai_plan_from_decision(
        request=request,
        node_capacities=node_capacities,
        decision={
            "reply": "建議優先開 pve-b。",
            "effective_resource_type": "lxc",
            "machines_to_open": [
                {"node": "pve-b", "instance_count": 2, "reason": "剩餘容量較大。"}
            ],
            "reasons": ["pve-b 的可用 CPU 與記憶體較多。"],
        },
        fallback_plan=fallback_plan,
    )

    assert ai_plan is not None
    assert ai_plan.recommended_node == "pve-b"
    assert ai_plan.assigned_instances == 2
    assert ai_plan.rationale[0] == "pve-b 的可用 CPU 與記憶體較多。"


def test_recommend_endpoint_returns_simplified_output(
    client: TestClient,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(advisor_router_module.settings, "enabled", True)

    async def fake_generate_recommendation(
        *,
        session: object,
        request: PlacementRequest,
    ) -> PlacementAdvisorResponse:
        del session, request
        return PlacementAdvisorResponse(
            reply="建議開 pve-a，因為剩餘容量較多。",
            machines_to_open=[],
            reasons=["pve-a 目前可用資源最多。"],
            current_status=[],
            ai_used=False,
        )

    monkeypatch.setattr(
        advisor_router_module,
        "generate_recommendation",
        fake_generate_recommendation,
    )

    response = client.post(
        f"{settings.API_V1_STR}/ai/pve-advisor/recommend",
        json={
            "container_type": "lxc",
            "cpu": 2,
            "memory_gb": 4,
            "disk": 30,
            "count": 2,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) >= {"reply", "machines_to_open", "reasons", "current_status"}
    assert data["reasons"][0] == "pve-a 目前可用資源最多。"
