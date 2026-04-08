"""Routes matching S3M-GUI's /api/v1/workspaces/* endpoint expectations.

Each route instantiates an adapter singleton and delegates to it.
Response shapes match the TypeScript interfaces in S3M-GUI exactly.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from src.api.gui_bridge.adapters.command_adapter import CommandAdapter
from src.api.gui_bridge.adapters.decision_adapter import DecisionAdapter
from src.api.gui_bridge.adapters.risk_adapter import RiskAdapter
from src.api.gui_bridge.adapters.cop_adapter import COPAdapter
from src.api.gui_bridge.adapters.readiness_adapter import ReadinessAdapter
from src.api.gui_bridge.adapters.cyber_adapter import CyberAdapter
from src.api.gui_bridge.adapters.surveillance_adapter import SurveillanceAdapter
from src.api.gui_bridge.adapters.sustainment_adapter import SustainmentAdapter
from src.api.gui_bridge.adapters.comms_adapter import CommsAdapter
from src.api.gui_bridge.adapters.simulation_adapter import SimulationAdapter
from src.api.gui_bridge.adapters.planning_adapter import PlanningAdapter

workspace_router = APIRouter(prefix="/workspaces", tags=["GUI Workspaces"])

# ── Adapter singletons ──────────────────────────────────────
_command = CommandAdapter()
_decisions = DecisionAdapter()
_risk = RiskAdapter()
_cop = COPAdapter()
_readiness = ReadinessAdapter()
_cyber = CyberAdapter()
_surveillance = SurveillanceAdapter()
_sustainment = SustainmentAdapter()
_comms = CommsAdapter()
_simulation = SimulationAdapter()
_planning = PlanningAdapter()


# ── Request/Response helpers ────────────────────────────────
class DecisionActionRequest(BaseModel):
    comment: str = ""


# ── Command Overview ────────────────────────────────────────
@workspace_router.get("/command/operational-context")
async def get_operational_context():
    return _command.get_operational_context().model_dump()


@workspace_router.get("/command/timeline-events")
async def get_timeline_events(
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    return _command.get_timeline_events(category=category, limit=limit).model_dump()


# ── COP ─────────────────────────────────────────────────────
@workspace_router.get("/cop/tracks")
async def get_cop_tracks():
    return _cop.get_tracks().model_dump()


@workspace_router.get("/cop/threat-tracks")
async def get_threat_tracks():
    return _cop.get_threat_tracks().model_dump()


# ── Decisions ───────────────────────────────────────────────
@workspace_router.get("/decisions/queue")
async def get_decision_queue():
    return _decisions.get_queue()


@workspace_router.post("/decisions/queue/{decision_id}/approve")
async def approve_decision(decision_id: str, body: DecisionActionRequest = DecisionActionRequest()):
    return await _decisions.approve(decision_id, comment=body.comment)


@workspace_router.post("/decisions/queue/{decision_id}/reject")
async def reject_decision(decision_id: str, body: DecisionActionRequest = DecisionActionRequest()):
    return await _decisions.reject(decision_id, comment=body.comment)


# ── Risk ────────────────────────────────────────────────────
@workspace_router.get("/risk/metrics")
async def get_risk_metrics():
    return _risk.get_metrics().model_dump()


# ── Readiness ───────────────────────────────────────────────
@workspace_router.get("/readiness/summary")
async def get_readiness_summary():
    return _readiness.get_summary().model_dump()


@workspace_router.get("/readiness/enriched")
async def get_readiness_enriched():
    return _readiness.get_enriched_summary()


# ── Surveillance / ISR ──────────────────────────────────────
@workspace_router.get("/surveillance/assets")
async def get_surveillance_assets():
    return _surveillance.get_assets()


@workspace_router.get("/surveillance/collection")
async def get_surveillance_collection():
    return _surveillance.get_collection_status()


@workspace_router.get("/surveillance/source-reliability")
async def get_surveillance_source_reliability():
    return _surveillance.get_source_reliability()


@workspace_router.get("/surveillance/fusion-brief")
async def get_surveillance_fusion_brief(region: str = Query("all")):
    return _surveillance.get_fusion_brief(region=region)


@workspace_router.get("/surveillance/watchlists")
async def get_surveillance_watchlists():
    return _surveillance.get_watchlists()


# ── Communications ──────────────────────────────────────────
@workspace_router.get("/communication/messages")
async def get_messages():
    return _comms.get_messages()


@workspace_router.post("/communication/messages/send")
async def send_message(payload: dict):
    return await _comms.send_message(payload)


# ── Cyber ───────────────────────────────────────────────────
@workspace_router.get("/cyber/incidents")
async def get_cyber_incidents():
    return _cyber.get_incidents()


@workspace_router.get("/cyber/resilience")
async def get_cyber_resilience():
    return _cyber.get_resilience()


# ── Simulation ──────────────────────────────────────────────
@workspace_router.get("/simulation/scenarios")
async def get_simulation_scenarios():
    return _simulation.get_scenarios()


@workspace_router.get("/simulation/catalog")
async def get_simulation_catalog():
    return _simulation.get_scenario_catalog()


@workspace_router.get("/simulation/aar/{scenario_id}")
async def get_simulation_aar(scenario_id: str):
    sid = str(scenario_id).strip()
    if not sid:
        raise HTTPException(status_code=400, detail="scenario_id is required")
    return _simulation.get_aar(sid)


@workspace_router.post("/simulation/compare/{scenario_id}")
async def compare_simulation_modes(scenario_id: str):
    sid = str(scenario_id).strip()
    if not sid:
        raise HTTPException(status_code=400, detail="scenario_id is required")
    return _simulation.run_comparison(sid)


# ── Sustainment ─────────────────────────────────────────────
@workspace_router.get("/sustainment/fleet")
async def get_fleet_status():
    return _sustainment.get_fleet()


@workspace_router.get("/sustainment/supply")
async def get_supply_status():
    return _sustainment.get_supply()


# ── Planning ────────────────────────────────────────────────
@workspace_router.get("/planning/phases")
async def get_planning_phases():
    return _planning.get_phases()


@workspace_router.get("/planning/coas")
async def get_courses_of_action():
    return _planning.get_coas()
