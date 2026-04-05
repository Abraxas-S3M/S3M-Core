"""Safety control authority API routes for tactical command governance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from src.platforms.common.messages import (
    AuthorizationType,
    AuthorityLevel,
    InterlockState,
    OperatorAuthorization,
)
from src.safety.control_authority import (
    ControlAuthorityService,
    InterlockStateMachine,
    RangeComplianceEngine,
    SimModeGuard,
)

safety_router = APIRouter()

_control_authority = ControlAuthorityService()
_interlock_machines: Dict[str, InterlockStateMachine] = {}
_sim_mode_guard = SimModeGuard()
_range_engine = RangeComplianceEngine()
_control_authority_audit_log: List[Dict[str, Any]] = []
_range_violation_log: List[Dict[str, Any]] = []


class RegisterOperatorRequest(BaseModel):
    operator_id: str = Field(..., min_length=1, max_length=128)
    authority_level: str = Field(..., min_length=1, max_length=64)


class IssueAuthorizationRequest(BaseModel):
    operator_id: str = Field(..., min_length=1, max_length=128)
    auth_type: str = Field(..., min_length=1, max_length=64)
    ttl_seconds: int = Field(default=300, ge=1, le=86_400)


class InterlockTransitionRequest(BaseModel):
    requested_state: str = Field(..., min_length=1, max_length=64)
    auth_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class SetSimModeRequest(BaseModel):
    simulation_mode: bool
    reason: str = Field(default="", max_length=256)
    auth_id: str = Field(..., min_length=1, max_length=128)


class CoordinatePoint(BaseModel):
    x: float
    y: float


class AddGeofenceRequest(BaseModel):
    geofence_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    polygon: List[CoordinatePoint] = Field(..., min_length=3)
    policy: str = Field(..., min_length=1, max_length=32)

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in {"allowed", "forbidden"}:
            raise ValueError("policy must be 'allowed' or 'forbidden'")
        return cleaned


def _audit(action: str, details: Dict[str, Any]) -> None:
    _control_authority_audit_log.append(
        {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details,
        }
    )
    if len(_control_authority_audit_log) > 5000:
        del _control_authority_audit_log[:-5000]


def _parse_authority_level(raw_level: str) -> AuthorityLevel:
    normalized = raw_level.strip().lower()
    for level in AuthorityLevel:
        if level.value == normalized:
            return level
    raise HTTPException(status_code=400, detail=f"Unsupported authority_level: {raw_level}")


def _parse_auth_type(raw_type: str) -> AuthorizationType:
    normalized = raw_type.strip().lower()
    for auth_type in AuthorizationType:
        if auth_type.value == normalized:
            return auth_type
    raise HTTPException(status_code=400, detail=f"Unsupported auth_type: {raw_type}")


def _parse_interlock_state(raw_state: str) -> InterlockState:
    normalized = raw_state.strip().lower()
    for state in InterlockState:
        if state.value == normalized:
            return state
    raise HTTPException(status_code=400, detail=f"Unsupported interlock state: {raw_state}")


def _get_or_create_interlock(payload_id: str) -> InterlockStateMachine:
    machine = _interlock_machines.get(payload_id)
    if machine is None:
        machine = InterlockStateMachine(payload_id=payload_id)
        _interlock_machines[payload_id] = machine
        _audit("interlock_created", {"payload_id": payload_id, "state": machine.state.value})
    return machine


def _resolve_authorization(auth_id: str) -> OperatorAuthorization:
    if not _control_authority.validate_authorization(auth_id):
        raise HTTPException(status_code=403, detail="authorization token is invalid or expired")
    record = _control_authority._authorizations.get(auth_id)  # noqa: SLF001
    if record is None:
        raise HTTPException(status_code=404, detail="authorization record not found")
    return OperatorAuthorization(operator_id=record.operator_id, auth_type=record.auth_type, auth_id=record.auth_id)


def _require_mission_commander(auth_id: str) -> str:
    auth = _resolve_authorization(auth_id)
    level = _control_authority._operators.get(auth.operator_id)  # noqa: SLF001
    if level is not AuthorityLevel.MISSION_COMMANDER:
        raise HTTPException(status_code=403, detail="MISSION_COMMANDER authorization is required")
    return auth.operator_id


@safety_router.post("/api/safety/operators")
async def register_operator(req: RegisterOperatorRequest) -> Dict[str, Any]:
    level = _parse_authority_level(req.authority_level)
    try:
        _control_authority.register_operator(req.operator_id, level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("operator_registered", {"operator_id": req.operator_id, "authority_level": level.value})
    return {"operator_id": req.operator_id, "authority_level": level.value}


@safety_router.post("/api/safety/authorize")
async def issue_authorization(req: IssueAuthorizationRequest) -> Dict[str, Any]:
    auth_type = _parse_auth_type(req.auth_type)
    try:
        auth = _control_authority.issue_authorization(
            operator_id=req.operator_id,
            auth_type=auth_type,
            ttl_seconds=req.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = _control_authority._authorizations.get(auth.auth_id)  # noqa: SLF001
    expires_at = record.expires_at.isoformat() if record else None
    _audit(
        "authorization_issued",
        {
            "auth_id": auth.auth_id,
            "operator_id": auth.operator_id,
            "auth_type": auth.auth_type.value,
            "expires_at": expires_at,
        },
    )
    return {
        "auth_id": auth.auth_id,
        "operator_id": auth.operator_id,
        "auth_type": auth.auth_type.value,
        "expires_at": expires_at,
    }


@safety_router.get("/api/safety/authorize/{auth_id}/validate")
async def validate_authorization(auth_id: str) -> Dict[str, Any]:
    valid = _control_authority.validate_authorization(auth_id)
    _audit("authorization_validated", {"auth_id": auth_id, "valid": valid})
    return {"auth_id": auth_id, "valid": valid}


@safety_router.post("/api/safety/authorize/{auth_id}/revoke")
async def revoke_authorization(auth_id: str) -> Dict[str, Any]:
    _control_authority.revoke_authorization(auth_id)
    _audit("authorization_revoked", {"auth_id": auth_id})
    return {"auth_id": auth_id, "revoked": True}


@safety_router.post("/api/safety/emergency-stop")
async def emergency_stop_all_platforms() -> Dict[str, Any]:
    for machine in _interlock_machines.values():
        machine.emergency_stop()
    payload_states = {payload_id: machine.state.value for payload_id, machine in _interlock_machines.items()}
    _audit("emergency_stop", {"payload_count": len(payload_states)})
    return {"status": "safe", "payload_states": payload_states}


@safety_router.get("/api/safety/audit-log")
async def get_control_authority_audit_log() -> Dict[str, Any]:
    return {"entries": list(_control_authority_audit_log), "total": len(_control_authority_audit_log)}


@safety_router.get("/api/safety/interlocks/{payload_id}")
async def get_interlock_state(payload_id: str) -> Dict[str, Any]:
    machine = _get_or_create_interlock(payload_id)
    return {"payload_id": payload_id, "state": machine.state.value}


@safety_router.post("/api/safety/interlocks/{payload_id}/transition")
async def transition_interlock_state(payload_id: str, req: InterlockTransitionRequest) -> Dict[str, Any]:
    machine = _get_or_create_interlock(payload_id)
    requested_state = _parse_interlock_state(req.requested_state)
    auth = _resolve_authorization(req.auth_id) if req.auth_id else None
    transitioned = machine.transition(requested_state=requested_state, auth=auth)
    if not transitioned:
        _audit(
            "interlock_transition_denied",
            {"payload_id": payload_id, "from_state": machine.state.value, "requested_state": requested_state.value},
        )
        raise HTTPException(status_code=403, detail="interlock transition denied")
    _audit("interlock_transition", {"payload_id": payload_id, "state": machine.state.value})
    return {"payload_id": payload_id, "state": machine.state.value}


@safety_router.get("/api/safety/sim-mode")
async def get_sim_mode() -> Dict[str, Any]:
    return {
        "simulation_mode": _sim_mode_guard.simulation_mode,
        "reason": _sim_mode_guard.reason,
        "can_engage": _sim_mode_guard.can_engage(),
    }


@safety_router.post("/api/safety/sim-mode")
async def set_sim_mode(req: SetSimModeRequest) -> Dict[str, Any]:
    operator_id = _require_mission_commander(req.auth_id)
    _sim_mode_guard.simulation_mode = req.simulation_mode
    _sim_mode_guard.reason = req.reason or ("simulation" if req.simulation_mode else "live")
    _audit(
        "sim_mode_changed",
        {
            "operator_id": operator_id,
            "simulation_mode": _sim_mode_guard.simulation_mode,
            "reason": _sim_mode_guard.reason,
        },
    )
    return {
        "simulation_mode": _sim_mode_guard.simulation_mode,
        "reason": _sim_mode_guard.reason,
        "can_engage": _sim_mode_guard.can_engage(),
    }


@safety_router.post("/api/safety/geofence")
async def add_geofence(req: AddGeofenceRequest) -> Dict[str, Any]:
    geofence_id = req.geofence_id or str(uuid.uuid4())
    polygon = [(point.x, point.y) for point in req.polygon]
    try:
        _range_engine.add_geofence(geofence_id=geofence_id, polygon_xy=polygon, policy=req.policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("geofence_added", {"geofence_id": geofence_id, "policy": req.policy, "points": len(polygon)})
    return {"geofence_id": geofence_id, "policy": req.policy, "points": polygon}


@safety_router.get("/api/safety/range-violations")
async def get_range_violations(
    platform_id: Optional[str] = Query(default=None),
    x: Optional[float] = Query(default=None),
    y: Optional[float] = Query(default=None),
    z: Optional[float] = Query(default=None),
) -> Dict[str, Any]:
    if platform_id is not None or x is not None or y is not None or z is not None:
        if platform_id is None or x is None or y is None or z is None:
            raise HTTPException(
                status_code=400,
                detail="platform_id, x, y, and z must all be provided together for a compliance check",
            )
        compliant = _range_engine.check_position(platform_id=platform_id, position=(x, y, z))
        if not compliant:
            _range_violation_log.append(
                {
                    "violation_id": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "platform_id": platform_id,
                    "position": {"x": x, "y": y, "z": z},
                    "reason": "position outside allowed range or inside forbidden geofence",
                }
            )
            if len(_range_violation_log) > 5000:
                del _range_violation_log[:-5000]
            _audit("range_violation", {"platform_id": platform_id, "x": x, "y": y, "z": z})
    return {"violations": list(_range_violation_log), "total": len(_range_violation_log)}
