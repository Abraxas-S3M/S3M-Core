"""FastAPI routes for interceptor guidance operations.

Military context:
Exposes command-post controls for launch, guidance, and autonomous handoff to
match the Krechet interceptor guidance workflow in an air-gapped deployment.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from fastapi import APIRouter, HTTPException

from services.interceptor.interceptor_manager import InterceptorManager
from services.interceptor.models import GuidanceMode, InterceptorConfig

router = APIRouter(prefix="/interceptor", tags=["interceptor"])
_MANAGER = InterceptorManager()


def _parse_vector3(raw: Any, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise HTTPException(status_code=400, detail=f"{field_name} must be [x_m, y_m, z_m]")
    try:
        return (float(raw[0]), float(raw[1]), float(raw[2]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} values must be numeric") from exc


def _build_config(payload: Dict[str, Any]) -> InterceptorConfig:
    try:
        return InterceptorConfig(
            interceptor_type=str(payload["interceptor_type"]),
            name_en=str(payload["name_en"]),
            name_ar=str(payload["name_ar"]),
            max_speed_mps=float(payload["max_speed_mps"]),
            max_acceleration_mps2=float(payload["max_acceleration_mps2"]),
            update_rate_hz=float(payload.get("update_rate_hz", 20.0)),
            navigation_constant=float(payload.get("navigation_constant", 3.0)),
            lead_bias=float(payload.get("lead_bias", 1.0)),
            terminal_approach_range_m=float(payload.get("terminal_approach_range_m", 1200.0)),
            autonomous_engagement_range_m=float(payload.get("autonomous_engagement_range_m", 10.0)),
            miss_abort_distance_m=float(payload.get("miss_abort_distance_m", 600.0)),
            preferred_mode=GuidanceMode(payload.get("preferred_mode", GuidanceMode.PROPORTIONAL_NAVIGATION.value)),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing config field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid interceptor config: {exc}") from exc


@router.post("/register")
async def register_interceptor(payload: Dict[str, Any]) -> Dict[str, Any]:
    interceptor_id = str(payload.get("interceptor_id", "")).strip()
    if not interceptor_id:
        raise HTTPException(status_code=400, detail="interceptor_id is required")
    config_payload = payload.get("config")
    if not isinstance(config_payload, dict):
        raise HTTPException(status_code=400, detail="config object is required")
    config = _build_config(config_payload)
    try:
        status = _MANAGER.register_interceptor(interceptor_id=interceptor_id, config=config)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": status}


@router.post("/{interceptor_id}/launch")
async def launch_interceptor(interceptor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    altitude = float(payload.get("takeoff_altitude_m", 120.0))
    try:
        status = _MANAGER.launch_interceptor(interceptor_id, takeoff_altitude_m=altitude)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": status}


@router.post("/{interceptor_id}/assign-target")
async def assign_target(interceptor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        status = _MANAGER.assign_target(
            interceptor_id=interceptor_id,
            target_id=str(payload["target_id"]),
            target_position_m=_parse_vector3(payload["target_position_m"], "target_position_m"),
            target_velocity_mps=_parse_vector3(payload.get("target_velocity_mps", (0.0, 0.0, 0.0)), "target_velocity_mps"),
            target_classification=str(payload.get("target_classification", "unknown")),
            request_allocation=bool(payload.get("request_allocation", True)),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": status}


@router.post("/{interceptor_id}/guide")
async def guide_interceptor(interceptor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    dt_s = payload.get("dt_s")
    try:
        solution = _MANAGER.guide_interceptor(interceptor_id=interceptor_id, dt_s=float(dt_s) if dt_s else None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"solution": solution.to_dict()}


@router.post("/{interceptor_id}/miss-reengage")
async def miss_reengage(interceptor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    position = payload.get("updated_target_position_m")
    velocity = payload.get("updated_target_velocity_mps")
    result = _MANAGER.report_miss_and_reengage(
        interceptor_id=interceptor_id,
        updated_target_position_m=_parse_vector3(position, "updated_target_position_m") if position else None,
        updated_target_velocity_mps=_parse_vector3(velocity, "updated_target_velocity_mps") if velocity else None,
    )
    return {"reengagement": str(result)}


@router.get("/{interceptor_id}/status")
async def interceptor_status(interceptor_id: str) -> Dict[str, Any]:
    try:
        status = _MANAGER.get_interceptor_status(interceptor_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": status}


@router.get("/fleet/status")
async def fleet_status() -> Dict[str, Any]:
    return {"fleet": _MANAGER.list_interceptors()}


@router.get("/health")
async def health() -> Dict[str, Any]:
    return _MANAGER.health_check()
