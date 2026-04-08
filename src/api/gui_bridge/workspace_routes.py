"""Routes matching S3M-GUI's /api/v1/workspaces/* endpoint expectations.

Each route instantiates an adapter singleton and delegates to it.
Response shapes match the TypeScript interfaces in S3M-GUI exactly.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, Field

from src.api.gui_bridge.adapters.command_adapter import CommandAdapter
from src.api.gui_bridge.adapters.agent_adapter import AgentAdapter
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
from src.api.gui_bridge.models.gui_schemas import GUIAgentProgramRequest
from src.command.action_board import ActionBoard

workspace_router = APIRouter(prefix="/workspaces", tags=["GUI Workspaces"])

# ── Adapter singletons ──────────────────────────────────────
_command = CommandAdapter()
_agent = AgentAdapter()
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
_action_board = ActionBoard()


# ── Request/Response helpers ────────────────────────────────
class DecisionActionRequest(BaseModel):
    comment: str = ""


class CyberAttackRequest(BaseModel):
    playbookId: Optional[str] = None
    adversaryId: Optional[str] = None
    targets: List[str] = Field(default_factory=list)
    approvalToken: Optional[str] = None
    objective: str = ""
    parameters: dict = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanningSuggestionsRequest(BaseModel):
    plan_context: str = ""


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


@workspace_router.get("/command/agents")
async def get_agents():
    agents = _agent.get_agents()
    return {"agents": [a.model_dump() for a in agents]}


@workspace_router.get("/command/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    try:
        return _agent.get_agent_detail(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc


@workspace_router.post("/command/agents/{agent_id}/program")
async def program_agent(agent_id: str, payload: GUIAgentProgramRequest):
    if payload.agentId != agent_id:
        raise HTTPException(status_code=422, detail="agentId in body must match path agent_id")
    try:
        return _agent.program_agent(
            agent_id=agent_id,
            instructions=payload.instructions,
            language=payload.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc


@workspace_router.get("/command/action-board")
async def get_action_board():
    return _command.get_action_board()


@workspace_router.get("/command/force-structure")
async def get_force_structure():
    return _command.get_force_structure()


@workspace_router.post("/command/action-board")
async def create_action_board_task(payload: ActionBoardCreateRequest):
    task = _action_board.add_task(
        title=payload.title,
        urgency=payload.urgency,
        impact=payload.impact,
        assignee=payload.assignee,
        status=payload.status,
        linked_decision_id=payload.linkedDecisionId,
    )
    return task.model_dump()


@workspace_router.patch("/command/action-board/{task_id}")
async def update_action_board_task(task_id: str, payload: ActionBoardUpdateRequest):
    task = _action_board.update_task(
        task_id=task_id,
        title=payload.title,
        urgency=payload.urgency,
        impact=payload.impact,
        assignee=payload.assignee,
        status=payload.status,
        linked_decision_id=payload.linkedDecisionId,
    )
    if not task:
        raise HTTPException(status_code=404, detail=f"Action task '{task_id}' not found")
    return task.model_dump()


# ── COP ─────────────────────────────────────────────────────
@workspace_router.get("/cop/tracks")
async def get_cop_tracks():
    return _cop.get_tracks().model_dump()


@workspace_router.get("/cop/threat-tracks")
async def get_threat_tracks():
    return _cop.get_threat_tracks().model_dump()


@workspace_router.get("/cop/replay")
async def get_cop_replay(
    start_time: str = Query(..., description="ISO-8601 replay window start"),
    end_time: str = Query(..., description="ISO-8601 replay window end"),
):
    return _cop.get_replay(start_time=start_time, end_time=end_time)


@workspace_router.get("/cop/mission-layer")
async def get_cop_mission_layer(
    mission_id: Optional[str] = Query(None, description="Optional mission identifier"),
):
    return _cop.get_mission_overlay(mission_id=mission_id)


# ── Decisions ───────────────────────────────────────────────
@workspace_router.get("/decisions/queue")
async def get_decision_queue():
    return _decisions.get_queue()


@workspace_router.get("/decisions/queue/{decision_id}/explain")
async def get_decision_explanation(decision_id: str):
    return _decisions.get_explanation(decision_id)


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


@workspace_router.post("/risk/what-if")
async def risk_what_if(scenario: dict):
    return _risk.get_what_if(scenario)


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


@workspace_router.get("/surveillance/watchlists/{category}")
async def get_surveillance_watchlist_category(category: str):
    try:
        return _surveillance.get_watchlist_category(category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@workspace_router.post("/surveillance/watchlists/{category}")
async def create_surveillance_watchlist_entity(category: str, payload: dict):
    try:
        return _surveillance.upsert_watchlist_entity(category, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@workspace_router.delete("/surveillance/watchlists/{category}/{entity_id}")
async def delete_surveillance_watchlist_entity(category: str, entity_id: str):
    try:
        result = _surveillance.delete_watchlist_entity(category, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="watchlist entity not found")
    return result


# ── Communications ──────────────────────────────────────────
@workspace_router.get("/communication/messages")
async def get_messages():
    return _comms.get_messages()


@workspace_router.post("/communication/messages/send")
async def send_message(payload: dict):
    return await _comms.send_message(payload)


@workspace_router.get("/communication/bearer-health")
async def get_bearer_health():
    return _comms.get_bearer_health()


@workspace_router.post("/communication/degradation-advice")
async def get_degradation_advice(payload: Optional[dict] = None):
    return _comms.get_degradation_advice(payload)


# ── Cyber ───────────────────────────────────────────────────
@workspace_router.get("/cyber/incidents")
async def get_cyber_incidents():
    return _cyber.get_incidents()


@workspace_router.get("/cyber/resilience")
async def get_cyber_resilience():
    return _cyber.get_resilience()


@workspace_router.get("/cyber/model-security")
async def get_model_security():
    return _cyber.get_model_security()


@workspace_router.get("/cyber/trust-fabric")
async def get_trust_fabric():
    return _cyber.get_trust_fabric()


@workspace_router.get("/cyber/attack-capabilities")
async def get_attack_capabilities():
    return _cyber.get_attack_capabilities()


@workspace_router.post("/cyber/attack/plan")
async def plan_cyber_attack(body: CyberAttackRequest):
    try:
        from services.cyber.offensive.caldera_bridge import CalderaBridge

        bridge = CalderaBridge()
        adversary_id = (body.adversaryId or body.playbookId or "").strip()
        targets = body.targets if body.targets else ["sim-target-001"]
        operation_id = bridge.create_operation(
            adversary_id=adversary_id,
            targets=targets,
            approval_token=body.approvalToken or "",
        )
        return {
            "status": "planned",
            "operationId": operation_id,
            "plan": {
                "adversaryId": adversary_id,
                "targets": targets,
                "objective": body.objective,
                "parameters": body.parameters,
            },
            "updatedAt": _now_iso(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@workspace_router.get("/cyber/attack/{operation_id}/status")
async def get_cyber_attack_status(operation_id: str):
    try:
        from services.cyber.offensive.caldera_bridge import CalderaBridge

        bridge = CalderaBridge()
        status = bridge.get_operation_status(operation_id)
        return {"operationId": operation_id, "status": status, "updatedAt": _now_iso()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@workspace_router.post("/cyber/attack/execute")
async def execute_cyber_attack(body: CyberAttackRequest):
    return {
        "status": "queued",
        "execution": {
            "playbookId": body.playbookId,
            "objective": body.objective,
            "parameters": body.parameters,
        },
        "updatedAt": _now_iso(),
    }


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


@workspace_router.get("/sustainment/maintenance/predictions")
async def get_maintenance_predictions():
    return _sustainment.get_predictions()


@workspace_router.get("/sustainment/supply-twin")
async def get_supply_twin_status():
    return _sustainment.get_supply_twin()


# ── Planning ────────────────────────────────────────────────
@workspace_router.get("/planning/phases")
async def get_planning_phases():
    return _planning.get_phases()


@workspace_router.get("/planning/coas")
async def get_courses_of_action():
    return _planning.get_coas()


@workspace_router.get("/planning/replan-triggers")
async def get_replan_triggers():
    return _planning.get_replan_triggers()


@workspace_router.post("/planning/suggestions")
async def get_planning_suggestions(payload: PlanningSuggestionsRequest = PlanningSuggestionsRequest()):
    return _planning.get_suggestions(plan_context=payload.plan_context)
