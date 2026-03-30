from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import DefaultScenarioResponse, SimulationRequest, SimulationResponse
from app.services import simulator_service


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/scenario/default", response_model=DefaultScenarioResponse)
def default_scenario() -> DefaultScenarioResponse:
    return simulator_service.build_default_scenario()


@router.post("/simulate", response_model=SimulationResponse)
def simulate(request: SimulationRequest) -> SimulationResponse:
    try:
        return simulator_service.run_simulation(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
