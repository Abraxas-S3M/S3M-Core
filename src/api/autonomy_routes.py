"""FastAPI routes for S3M Phase 6 autonomy and swarm operations.

These endpoints expose tactical autonomy controls for agent registration,
mission orchestration, swarm command-and-control, RL policy management, and
XAI assurance workflows in an air-gapped deployment.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import copy
import uuid

import yaml
from fastapi import APIRouter, HTTPException, Query

from src.api.autonomy_models import (
    AgentResponse,
    AutonomyStatusResponse,
    DecisionResponse,
    ExplanationResponse,
    FormationRequest,
    MissionResponse,
    NLCommandRequest,
    RegisterAgentRequest,
    StartMissionRequest,
    SwarmCommandRequest,
    SwarmStatusResponse,
    TrainRLRequest,
)
from src.autonomy.behavior_trees import MissionExecutor, MissionTree
from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    CommandType,
    DecisionType,
    FormationType,
    Mission,
    MissionStatus,
    MissionType,
    SwarmCommand,
)
from src.autonomy.rl import DroneSwarmEnv, MilitaryEnvironment, RLAgentManager
from src.autonomy.realtime_arbiter import RealtimeDecisionArbiter
from src.autonomy.swarm import NLCommander, SwarmCoordinator
from src.autonomy.xai import AssuranceChecker, DecisionExplainer, DecisionLog


autonomy_router = APIRouter()


class _AutonomyRuntime:
    def __init__(self) -> None:
        self.coordinator = SwarmCoordinator(max_agents=50)
        self.rl_manager = RLAgentManager(backend="auto")
        self.decision_log = DecisionLog(max_entries=50000)
        self.decision_explainer = DecisionExplainer()
        self.assurance = AssuranceChecker(risk_threshold=0.7, confidence_threshold=0.3)
        self.nl_commander = NLCommander()
        self.realtime_arbiter = RealtimeDecisionArbiter()
        self.executors: Dict[str, MissionExecutor] = {}
        self.audit_log: List[Dict[str, Any]] = []

    def log(self, action: str, details: Dict[str, Any]) -> None:
        self.audit_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "details": copy.deepcopy(details),
            }
        )
        if len(self.audit_log) > 5000:
            self.audit_log = self.audit_log[-5000:]


runtime = _AutonomyRuntime()


def _map_mission_type(value: str) -> MissionType:
    try:
        return MissionType(value)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid mission_type: {value}") from exc


def _map_mission_status(value: str) -> MissionStatus:
    try:
        return MissionStatus(value)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid mission_status: {value}") from exc


def _create_mission(payload: Dict[str, Any]) -> Mission:
    mission_id = str(payload.get("mission_id") or f"msn-{uuid.uuid4().hex[:8]}")
    mission_type = _map_mission_type(str(payload.get("mission_type", "custom")))
    status = _map_mission_status(str(payload.get("status", "pending")))
    title = str(payload.get("title") or payload.get("name") or mission_id)
    description = str(payload.get("description") or "Mission generated from autonomy request")
    waypoints = payload.get("waypoints", [])
    if not isinstance(waypoints, list):
        raise HTTPException(status_code=422, detail="waypoints must be a list")
    wp_tuples = []
    for waypoint in waypoints:
        if not isinstance(waypoint, (list, tuple)) or len(waypoint) != 3:
            raise HTTPException(status_code=422, detail="each waypoint must be [x, y, z]")
        wp_tuples.append((float(waypoint[0]), float(waypoint[1]), float(waypoint[2])))

    try:
        mission = Mission(
            mission_id=mission_id,
            mission_type=mission_type,
            status=status,
            title=title,
            description=description,
            assigned_agents=[str(a) for a in payload.get("assigned_agents", [])],
            waypoints=wp_tuples,
            priority=int(payload.get("priority", 3)),
            rules_of_engagement=str(payload.get("rules_of_engagement", "weapons_hold")),
            parameters=dict(payload.get("parameters", {})),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return mission


def _serialize_mission(mission: Mission) -> MissionResponse:
    data = mission.to_dict()
    data["mission_type"] = MissionType(data["mission_type"])
    data["status"] = MissionStatus(data["status"])
    return MissionResponse(**data)


def _serialize_agent(agent: AgentInfo) -> AgentResponse:
    data = agent.to_dict()
    data["role"] = AgentRole(data["role"])
    data["state"] = AgentState(data["state"])
    data["capability"] = AgentCapability(data["capability"])
    data["position"] = tuple(data.get("position", (0.0, 0.0, 0.0)))
    return AgentResponse(**data)


def _resolve_agent_state(value: Optional[str]) -> Optional[AgentState]:
    if not value:
        return None
    try:
        return AgentState(value)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid agent state: {value}")


def _resolve_agent_role(value: Optional[str]) -> Optional[AgentRole]:
    if not value:
        return None
    try:
        return AgentRole(value)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid agent role: {value}")


def _resolve_agent_capability(value: Optional[str]) -> Optional[AgentCapability]:
    if not value:
        return None
    try:
        return AgentCapability(value)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid agent capability: {value}")


@autonomy_router.get("/autonomy/status", response_model=AutonomyStatusResponse)
async def get_autonomy_status() -> AutonomyStatusResponse:
    """Full autonomy subsystem health snapshot for tactical monitoring."""
    return AutonomyStatusResponse(
        status="operational",
        rl=runtime.rl_manager.health_check(),
        swarm=runtime.coordinator.health_check(),
        xai={
            "decision_log": runtime.decision_log.get_stats(),
            "review_queue": len(runtime.assurance.get_review_queue()),
        },
        missions=len(runtime.coordinator.missions),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@autonomy_router.get("/autonomy/agents", response_model=List[AgentResponse])
async def list_agents(
    state: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    capability: Optional[str] = Query(default=None),
) -> List[AgentResponse]:
    """List registered autonomous agents with optional filters."""
    agents = runtime.coordinator.get_agents(
        state=_resolve_agent_state(state),
        role=_resolve_agent_role(role),
        capability=_resolve_agent_capability(capability),
    )
    return [_serialize_agent(agent) for agent in agents]


@autonomy_router.get("/autonomy/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str) -> AgentResponse:
    """Get detailed agent state by identifier."""
    agent = runtime.coordinator.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _serialize_agent(agent)


@autonomy_router.post("/autonomy/agents/register", response_model=AgentResponse)
async def register_agent(request: RegisterAgentRequest) -> AgentResponse:
    """Register new autonomous platform into swarm roster."""
    try:
        agent = AgentInfo(
            agent_id=request.agent_id,
            role=AgentRole(request.role),
            state=AgentState(request.state),
            capability=AgentCapability(request.capability),
            position=(float(request.position[0]), float(request.position[1]), float(request.position[2])),
            heading=float(request.heading),
            speed=float(request.speed),
            battery_pct=float(request.battery_pct),
            fuel_pct=float(request.fuel_pct),
            current_mission=request.current_mission,
            sensor_loadout=list(request.sensor_loadout),
            weapon_loadout=list(request.weapon_loadout),
            comms_status=request.comms_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    runtime.coordinator.register_agent(agent)
    runtime.log("register_agent", {"agent_id": agent.agent_id})
    return _serialize_agent(agent)


@autonomy_router.patch("/autonomy/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, payload: Dict[str, Any]) -> AgentResponse:
    """Update mutable agent state fields for tactical operations."""
    try:
        runtime.coordinator.update_agent(agent_id, **payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Agent not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    agent = runtime.coordinator.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    runtime.log("update_agent", {"agent_id": agent_id, "fields": list(payload.keys())})
    return _serialize_agent(agent)


@autonomy_router.delete("/autonomy/agents/{agent_id}")
async def remove_agent(agent_id: str) -> Dict[str, str]:
    """Remove agent from swarm roster."""
    runtime.coordinator.remove_agent(agent_id)
    runtime.log("remove_agent", {"agent_id": agent_id})
    return {"status": "removed", "agent_id": agent_id}


@autonomy_router.post("/autonomy/mission/start", response_model=MissionResponse)
async def start_mission(request: StartMissionRequest) -> MissionResponse:
    """Create and start mission from inline payload or mission YAML."""
    mission_payload: Dict[str, Any]
    if request.mission:
        mission_payload = request.mission.model_dump(mode="json")
    elif request.yaml_path:
        path = Path(request.yaml_path)
        if not path.is_absolute():
            path = Path("/workspace") / path
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Mission YAML not found: {request.yaml_path}")
        try:
            mission_yaml = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid mission YAML: {exc}") from exc
        mission_node = mission_yaml.get("mission", {}) if isinstance(mission_yaml, dict) else {}
        mission_payload = {
            "mission_id": f"msn-{uuid.uuid4().hex[:8]}",
            "mission_type": str(mission_node.get("type", "custom")),
            "status": "pending",
            "title": mission_node.get("name", "YAML Mission"),
            "description": mission_node.get("description", ""),
            "waypoints": mission_node.get("waypoints", []),
            "rules_of_engagement": mission_node.get("rules_of_engagement", "weapons_hold"),
            "priority": mission_node.get("priority", 3),
            "parameters": {"yaml_source": str(path), "tree": mission_node.get("tree", {})},
        }
    else:
        raise HTTPException(status_code=422, detail="Provide mission payload or yaml_path")

    mission = _create_mission(mission_payload)
    runtime.coordinator.assign_mission(mission)
    started = runtime.coordinator.start_mission(mission.mission_id)
    if not started:
        raise HTTPException(status_code=500, detail="Failed to start mission")

    tree_spec = mission.parameters.get("tree")
    if tree_spec:
        mission_yaml = {"mission": {"type": mission.mission_type.value, "tree": tree_spec}}
        mission_tree = MissionTree(mission_yaml)
        tree = mission_tree.build()
        context = {
            "mission_id": mission.mission_id,
            "battery_pct": 100.0,
            "rules_of_engagement": mission.rules_of_engagement,
            "waypoints": mission.waypoints,
            "agent_position": mission.waypoints[0] if mission.waypoints else (0.0, 0.0, 0.0),
            "base_position": mission.parameters.get("base_position", (0.0, 0.0, 0.0)),
            "decision_log": [],
            "available_agents": len(mission.assigned_agents),
        }
        executor = MissionExecutor(tree=tree, tick_rate_hz=10.0, arbiter=runtime.realtime_arbiter)
        runtime.executors[mission.mission_id] = executor
        executor.start(context)
        for _ in range(3):
            status = executor.tick()
            if status.value in {"success", "failure"}:
                break
        for decision in executor.get_decision_log():
            runtime.decision_log.log(decision)
    runtime.log("start_mission", {"mission_id": mission.mission_id})
    return _serialize_mission(mission)


@autonomy_router.post("/autonomy/mission/{mission_id}/abort")
async def abort_mission(mission_id: str) -> Dict[str, str]:
    """Abort active mission and release assigned agents."""
    runtime.coordinator.abort_mission(mission_id)
    executor = runtime.executors.get(mission_id)
    if executor:
        executor.abort()
    runtime.log("abort_mission", {"mission_id": mission_id})
    return {"status": "aborted", "mission_id": mission_id}


@autonomy_router.get("/autonomy/mission/{mission_id}", response_model=MissionResponse)
async def get_mission(mission_id: str) -> MissionResponse:
    """Retrieve mission details by mission ID."""
    mission = runtime.coordinator.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _serialize_mission(mission)


@autonomy_router.get("/autonomy/missions", response_model=List[MissionResponse])
async def list_missions() -> List[MissionResponse]:
    """List all registered missions."""
    return [_serialize_mission(mission) for mission in runtime.coordinator.missions.values()]


@autonomy_router.post("/autonomy/swarm/command")
async def issue_swarm_command(request: SwarmCommandRequest) -> Dict[str, Any]:
    """Issue structured swarm command through protocol validator."""
    try:
        cmd = SwarmCommand(
            command_id=f"cmd-{uuid.uuid4().hex[:8]}",
            command_type=CommandType(request.command_type),
            target_agents=list(request.target_agents),
            parameters=dict(request.parameters),
            issued_by=request.issued_by,
            priority=int(request.priority),
            ttl_seconds=float(request.ttl_seconds),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ok = runtime.coordinator.issue_command(cmd)
    runtime.log("issue_command", {"command_id": cmd.command_id, "accepted": ok})
    if not ok:
        raise HTTPException(status_code=400, detail="Command rejected by protocol validation")
    return {"status": "queued", "command": cmd.to_dict()}


@autonomy_router.post("/autonomy/swarm/command/nl")
async def issue_nl_command(request: NLCommandRequest) -> Dict[str, Any]:
    """Parse natural language command and issue resulting swarm command."""
    if request.language == "ar":
        command = runtime.nl_commander.parse_arabic_command(request.natural_language)
    else:
        command = runtime.nl_commander.parse_command(request.natural_language)
    ok = runtime.coordinator.issue_command(command)
    runtime.log(
        "issue_nl_command",
        {
            "language": request.language,
            "input": request.natural_language,
            "command_id": command.command_id,
            "accepted": ok,
        },
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Parsed command failed validation")
    return {"status": "queued", "command": command.to_dict()}


@autonomy_router.get("/autonomy/swarm/formation")
async def get_formation() -> Dict[str, Any]:
    """Return current swarm formation state."""
    formation = runtime.coordinator.current_formation
    if formation is None:
        return {"formation": None}
    return {"formation": formation}


@autonomy_router.post("/autonomy/swarm/formation")
async def set_formation(request: FormationRequest) -> Dict[str, Any]:
    """Set new swarm formation and queue command."""
    if not runtime.coordinator.agents:
        raise HTTPException(status_code=400, detail="No agents registered")
    try:
        formation_type = FormationType(request.formation_type)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid formation_type: {request.formation_type}")
    cmd = runtime.coordinator.set_formation(formation_type=formation_type, spacing=request.spacing)
    runtime.log("set_formation", {"formation_type": request.formation_type})
    return {"status": "queued", "command": cmd.to_dict()}


@autonomy_router.post("/autonomy/swarm/emergency-stop")
async def emergency_stop() -> Dict[str, Any]:
    """Issue emergency stop broadcast command."""
    cmd = runtime.coordinator.emergency_stop()
    runtime.log("emergency_stop", {"command_id": cmd.command_id})
    return {"status": "queued", "command": cmd.to_dict()}


@autonomy_router.get("/autonomy/swarm/status", response_model=SwarmStatusResponse)
async def get_swarm_status() -> SwarmStatusResponse:
    """Get aggregated swarm operational status."""
    status = runtime.coordinator.get_swarm_status()
    return SwarmStatusResponse(**status)


@autonomy_router.post("/autonomy/rl/train")
async def train_rl(request: TrainRLRequest) -> Dict[str, Any]:
    """Start RL training run using selected environment and algorithm."""
    env_name = request.env_name.lower()
    if env_name in {"military", "militaryenvironment"}:
        env = MilitaryEnvironment()
    elif env_name in {"drone_swarm", "swarm", "droneswarmenv"}:
        env = DroneSwarmEnv()
    else:
        raise HTTPException(status_code=422, detail=f"Unknown env_name: {request.env_name}")
    agent_id = runtime.rl_manager.create_agent(env=env, algorithm=request.algorithm)
    metrics = runtime.rl_manager.train(agent_id=agent_id, n_steps=request.n_steps)
    runtime.log("rl_train", {"agent_id": agent_id, "metrics": metrics})
    return {"agent_id": agent_id, "metrics": metrics}


@autonomy_router.get("/autonomy/rl/policies")
async def list_policies() -> Dict[str, Any]:
    """List stored policy metadata from policy registry."""
    return {"policies": runtime.rl_manager.registry.list_policies()}


@autonomy_router.post("/autonomy/rl/policies/{name}/load")
async def load_policy(name: str) -> Dict[str, str]:
    """Load policy by name into active RL manager."""
    try:
        agent_id = runtime.rl_manager.load(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Policy not found: {name}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Policy load failed: {exc}") from exc
    runtime.log("rl_load_policy", {"name": name, "agent_id": agent_id})
    return {"status": "loaded", "agent_id": agent_id}


@autonomy_router.get("/autonomy/decisions", response_model=List[DecisionResponse])
async def query_decisions(
    agent_id: Optional[str] = Query(default=None),
    decision_type: Optional[str] = Query(default=None),
    mission_id: Optional[str] = Query(default=None),
    requires_review: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> List[DecisionResponse]:
    """Query decision log with tactical filters."""
    decision_type_enum: Optional[DecisionType] = None
    if decision_type:
        try:
            decision_type_enum = DecisionType(decision_type)
        except Exception:
            raise HTTPException(status_code=422, detail=f"Invalid decision_type: {decision_type}")
    decisions = runtime.decision_log.query(
        agent_id=agent_id,
        decision_type=decision_type_enum,
        mission_id=mission_id,
        requires_review=requires_review,
        limit=limit,
    )
    payloads: List[DecisionResponse] = []
    for decision in decisions:
        d = decision.to_dict()
        d["decision_type"] = DecisionType(d["decision_type"])
        payloads.append(DecisionResponse(**d))
    return payloads


@autonomy_router.get("/autonomy/decisions/{decision_id}", response_model=DecisionResponse)
async def get_decision(decision_id: str) -> DecisionResponse:
    """Return single decision record by ID."""
    decision = runtime.decision_log.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    payload = decision.to_dict()
    payload["decision_type"] = DecisionType(payload["decision_type"])
    return DecisionResponse(**payload)


@autonomy_router.get("/autonomy/decisions/{decision_id}/explain", response_model=ExplanationResponse)
async def explain_decision(decision_id: str) -> ExplanationResponse:
    """Generate structured XAI explanation for a decision."""
    decision = runtime.decision_log.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    explanation = runtime.decision_explainer.explain(decision)
    return ExplanationResponse(
        decision_id=decision_id,
        summary=str(explanation.get("summary", "")),
        factors=list(explanation.get("factors", [])),
        alternatives=list(explanation.get("alternatives", [])),
        risk_assessment=dict(explanation.get("risk_assessment", {})),
        recommendation=str(explanation.get("recommendation", "")),
    )


@autonomy_router.get("/autonomy/decisions/review-queue", response_model=List[DecisionResponse])
async def get_review_queue() -> List[DecisionResponse]:
    """List decisions pending human review."""
    decisions = runtime.assurance.get_review_queue()
    payloads: List[DecisionResponse] = []
    for decision in decisions:
        d = decision.to_dict()
        d["decision_type"] = DecisionType(d["decision_type"])
        payloads.append(DecisionResponse(**d))
    return payloads


@autonomy_router.post("/autonomy/decisions/{decision_id}/approve")
async def approve_decision(decision_id: str, payload: Dict[str, str]) -> Dict[str, str]:
    """Mark review-queued decision as approved by human reviewer."""
    reviewer = str(payload.get("reviewer", "operator"))
    try:
        runtime.assurance.approve(decision_id=decision_id, reviewer=reviewer)
    except KeyError:
        raise HTTPException(status_code=404, detail="Decision not in review queue")
    runtime.log("decision_approve", {"decision_id": decision_id, "reviewer": reviewer})
    return {"status": "approved", "decision_id": decision_id, "reviewer": reviewer}


@autonomy_router.post("/autonomy/decisions/{decision_id}/reject")
async def reject_decision(decision_id: str, payload: Dict[str, str]) -> Dict[str, str]:
    """Mark review-queued decision as rejected by human reviewer."""
    reviewer = str(payload.get("reviewer", "operator"))
    reason = str(payload.get("reason", "Not provided"))
    try:
        runtime.assurance.reject(decision_id=decision_id, reviewer=reviewer, reason=reason)
    except KeyError:
        raise HTTPException(status_code=404, detail="Decision not in review queue")
    runtime.log("decision_reject", {"decision_id": decision_id, "reviewer": reviewer, "reason": reason})
    return {"status": "rejected", "decision_id": decision_id, "reviewer": reviewer, "reason": reason}


@autonomy_router.post("/autonomy/arbiter/override")
async def force_arbiter_override(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Force manual real-time arbiter override from command authority."""
    action = str(payload.get("action", "hold_and_reassess"))
    source = str(payload.get("source", "operator"))
    reason = str(payload.get("reason", "manual override"))
    override = runtime.realtime_arbiter.force_override(action=action, source=source, reason=reason)
    runtime.log("arbiter_force_override", {"action": action, "source": source, "reason": reason})
    return {"status": "ok", "override": override}


@autonomy_router.delete("/autonomy/arbiter/override")
async def cancel_arbiter_override() -> Dict[str, Any]:
    """Cancel active manual real-time arbiter override."""
    cleared = runtime.realtime_arbiter.cancel_override()
    runtime.log("arbiter_cancel_override", {})
    return {"status": "ok", "cleared": cleared}


@autonomy_router.get("/autonomy/arbiter/state")
async def get_arbiter_state() -> Dict[str, Any]:
    """Return current real-time arbiter state and risk trend."""
    return runtime.realtime_arbiter.get_state()


@autonomy_router.get("/autonomy/arbiter/priorities")
async def get_arbiter_priorities() -> Dict[str, Any]:
    """Return active arbiter tactical priorities."""
    return {"active_priorities": runtime.realtime_arbiter.list_priorities()}
