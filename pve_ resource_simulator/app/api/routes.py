from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import (
    DefaultScenarioResponse,
    ProxmoxMonthlyAnalyticsResponse,
    SimulationRequest,
    SimulationResponse,
)
from app.services import proxmox_analytics_service, simulator_service


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/scenario/default", response_model=DefaultScenarioResponse)
def default_scenario() -> DefaultScenarioResponse:
    return simulator_service.build_default_scenario()


@router.get("/scenario/live", response_model=DefaultScenarioResponse)
async def live_scenario() -> DefaultScenarioResponse:
    try:
        return await simulator_service.build_live_scenario()
    except proxmox_analytics_service.ProxmoxAnalyticsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/simulate", response_model=SimulationResponse)
def simulate(request: SimulationRequest) -> SimulationResponse:
    try:
        return simulator_service.run_simulation(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/proxmox/monthly-analytics", response_model=ProxmoxMonthlyAnalyticsResponse)
async def proxmox_monthly_analytics() -> ProxmoxMonthlyAnalyticsResponse:
    try:
        return await proxmox_analytics_service.fetch_monthly_analytics()
    except proxmox_analytics_service.ProxmoxAnalyticsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
