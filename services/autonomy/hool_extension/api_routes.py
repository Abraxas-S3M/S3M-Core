"""FastAPI routes for HOOL autonomy extension management.

Military context:
These endpoints enforce pre-mission human authorization, mission envelope
validation, and operator override controls for autonomous platform operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from services.autonomy.hool_extension.hool_agent import HOOLAgent
from services.autonomy.hool_extension.models import CompanionCompute, MissionEnvelope, PlatformClass
from services.autonomy.hool_extension.platform_packager import PlatformPackager


router = APIRouter()

_ENVELOPES: Dict[str, Dict[str, Any]] = {}
_MISSIONS: Dict[str, Dict[str, Any]] = {}
_DECISIONS: Dict[str, List[Dict[str, Any]]] = {}
_PACKAGER = PlatformPackager()


@router.post("/hool/envelope/create")
async def create_envelope(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create mission envelope draft and validate commander signature presence."""
    if not payload.get("approval_signature"):
        raise HTTPException(status_code=400, detail="human approval signature required")
    try:
        envelope = MissionEnvelope(
            envelope_id=str(payload["envelope_id"]),
            mission_id=str(payload["mission_id"]),
            approved_by=str(payload.get("approved_by", "")),
            approved_at=datetime.fromisoformat(payload.get("approved_at") or datetime.now(timezone.utc).isoformat()),
            geofence_vertices=[tuple(v) for v in payload.get("geofence_vertices", [])],
            geofence_ceiling_m=float(payload.get("geofence_ceiling_m", 0.0)),
            geofence_floor_m=float(payload.get("geofence_floor_m", 0.0)),
            time_window=(
                datetime.fromisoformat(payload["time_window"][0]),
                datetime.fromisoformat(payload["time_window"][1]),
            ),
            roe_level=str(payload.get("roe_level", "weapons_hold")),
            max_targets=int(payload.get("max_targets", 0)),
            allowed_target_types=list(payload.get("allowed_target_types", [])),
            min_engagement_confidence=float(payload.get("min_engagement_confidence", 0.8)),
            min_battery_pct=float(payload.get("min_battery_pct", 20.0)),
            min_fuel_pct=float(payload.get("min_fuel_pct", 0.0)),
            max_comms_loss_seconds=float(payload.get("max_comms_loss_seconds", 120.0)),
            max_risk_score=float(payload.get("max_risk_score", 75.0)),
            max_escalation_level=int(payload.get("max_escalation_level", 3)),
            custom_constraints=dict(payload.get("custom_constraints", {})),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid envelope payload: {exc}") from exc

    ok, issues = envelope.validate()
    _ENVELOPES[envelope.envelope_id] = {
        "envelope": envelope,
        "approved": False,
        "approval_signature": payload.get("approval_signature"),
    }
    return {"valid": ok, "issues": issues, "envelope": envelope.to_dict()}


@router.post("/hool/envelope/{id}/approve")
async def approve_envelope(id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Approve envelope by human commander as mandatory pre-mission step."""
    row = _ENVELOPES.get(id)
    if not row:
        raise HTTPException(status_code=404, detail="envelope not found")
    commander = payload.get("commander_id")
    if not commander:
        raise HTTPException(status_code=400, detail="commander_id required")
    row["approved"] = True
    row["approved_by"] = commander
    row["approved_at"] = datetime.now(timezone.utc).isoformat()
    return {"status": "approved", "envelope_id": id, "approved_by": commander}


@router.post("/hool/mission/start")
async def start_hool_mission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Start HOOL mission only when associated envelope has been approved."""
    envelope_id = str(payload.get("envelope_id", ""))
    platform_value = str(payload.get("platform_class", PlatformClass.UAV_QUADROTOR.value))
    row = _ENVELOPES.get(envelope_id)
    if not row:
        raise HTTPException(status_code=404, detail="envelope not found")
    if not row.get("approved"):
        raise HTTPException(status_code=400, detail="envelope not approved")
    envelope = row["envelope"]
    try:
        platform = PlatformClass(platform_value)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid platform_class")

    agent = HOOLAgent(platform_class=platform, envelope=envelope)
    mission_id = envelope.mission_id
    _MISSIONS[mission_id] = {
        "agent": agent,
        "state": agent.state,
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _DECISIONS.setdefault(mission_id, [])
    return {"status": "started", "mission_id": mission_id, "platform": platform.value}


@router.post("/hool/mission/{id}/abort")
async def abort_hool_mission(id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Human abort override endpoint that is always available."""
    mission = _MISSIONS.get(id)
    if not mission:
        raise HTTPException(status_code=404, detail="mission not found")
    mission["status"] = "aborted"
    mission["state"].mode = "safe_mode"
    return {"status": "aborted", "mission_id": id, "reason": payload.get("reason", "operator_abort")}


@router.get("/hool/mission/{id}/state")
async def get_hool_mission_state(id: str) -> Dict[str, Any]:
    """Return current HOOL mission state for operator situational awareness."""
    mission = _MISSIONS.get(id)
    if not mission:
        raise HTTPException(status_code=404, detail="mission not found")
    state = mission["state"]
    return {
        "mission_id": state.mission_id,
        "mode": state.mode,
        "position": state.current_position,
        "battery_pct": state.battery_pct,
        "risk_score": state.risk_score,
        "violations": [v.__dict__ for v in state.violations],
        "status": mission["status"],
    }


@router.get("/hool/mission/{id}/decisions")
async def get_hool_mission_decisions(id: str) -> Dict[str, Any]:
    """Return HOOL decision log with XAI details for mission audit."""
    mission = _MISSIONS.get(id)
    if not mission:
        raise HTTPException(status_code=404, detail="mission not found")
    return {"mission_id": id, "decisions": list(_DECISIONS.get(id, []))}


@router.post("/hool/package")
async def package_hool(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate deployable HOOL package for selected platform class."""
    envelope_id = str(payload.get("envelope_id", ""))
    row = _ENVELOPES.get(envelope_id)
    if not row:
        raise HTTPException(status_code=404, detail="envelope not found")
    try:
        platform = PlatformClass(str(payload.get("platform_class")))
    except Exception:
        raise HTTPException(status_code=422, detail="invalid platform_class")

    package = _PACKAGER.package_for_platform(platform, row["envelope"], models=payload.get("models"))
    valid, issues = _PACKAGER.validate_package(package)
    return {"package": package, "valid": valid, "issues": issues}


@router.get("/hool/platforms")
async def list_hool_platforms() -> Dict[str, Any]:
    """List supported HOOL platforms and companion compute specifications."""
    data = []
    for platform in PlatformClass:
        compute = CompanionCompute.for_platform(platform)
        data.append(
            {
                "platform": platform.value,
                "cpu_model": compute.cpu_model,
                "ram_mb": compute.ram_mb,
                "gpu_available": compute.gpu_available,
                "llm_capable": compute.llm_capable,
            }
        )
    return {"platforms": data}


@router.get("/hool/status")
async def hool_status() -> Dict[str, Any]:
    """Return HOOL subsystem health and mission counters."""
    return {
        "status": "operational",
        "envelopes": len(_ENVELOPES),
        "missions": len(_MISSIONS),
        "active_missions": sum(1 for m in _MISSIONS.values() if m.get("status") == "active"),
    }
