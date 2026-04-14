"""FastAPI routes for interceptor guidance management.

Military context:
These routes expose command-post controls for interceptor assignment and
guidance-cycle updates in offline defensive engagement simulations.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from fastapi import APIRouter, HTTPException

from services.interceptor.interceptor_manager import InterceptorManager
from services.interceptor.models import HandoffCriteria, InterceptorConfig

router = APIRouter(prefix="/interceptor", tags=["interceptor"])

_manager = InterceptorManager()


def _require_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    return payload


def _require_text(payload: Dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{key} is required")
    return value


def _parse_vec3(raw_value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw_value, (list, tuple)) or len(raw_value) != 3:
        raise HTTPException(status_code=400, detail=f"{field_name} must be [x_m, y_m, z_m]")
    try:
        return (float(raw_value[0]), float(raw_value[1]), float(raw_value[2]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must contain numeric coordinates") from exc


@router.post("/register")
async def register_interceptor(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _require_payload(payload)
    try:
        config = InterceptorConfig(
            name_en=str(payload.get("name_en", "Interceptor")),
            name_ar=str(payload.get("name_ar", "طائرة اعتراض")),
            platform_type=str(payload.get("platform_type", "fixed_wing")),
            max_speed_mps=float(payload.get("max_speed_mps", 80.0)),
            nav_constant=float(payload.get("nav_constant", 4.0)),
            guidance_update_hz=float(payload.get("guidance_update_hz", 10.0)),
            position=_parse_vec3(payload.get("position", [0.0, 0.0, 0.0]), field_name="position"),
            handoff=HandoffCriteria(
                handoff_range_m=float(payload.get("handoff_range_m", 250.0)),
                terminal_range_m=float(payload.get("terminal_range_m", 500.0)),
            ),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registered = _manager.register_interceptor(config)
    return {"interceptor_id": registered.interceptor_id, "status": "registered"}


@router.post("/assign")
async def assign_target(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _require_payload(payload)
    intc_id = _require_text(payload, "interceptor_id")
    target_id = _require_text(payload, "target_id")
    if not _manager.assign_target(intc_id, target_id):
        raise HTTPException(status_code=404, detail="Interceptor not found")
    return {"interceptor_id": intc_id, "target_id": target_id, "status": "assigned"}


@router.post("/launch/{interceptor_id}")
async def launch(interceptor_id: str) -> Dict[str, Any]:
    if not _manager.launch(interceptor_id):
        raise HTTPException(status_code=404, detail="Interceptor not found or not assigned")
    return {"interceptor_id": interceptor_id, "status": "launched"}


@router.post("/radar-acquired/{interceptor_id}")
async def radar_acquired(interceptor_id: str) -> Dict[str, Any]:
    if not _manager.radar_acquired(interceptor_id):
        raise HTTPException(status_code=404, detail="Not found")
    return {"interceptor_id": interceptor_id, "status": "radar_acquired"}


@router.post("/guide")
async def guide_cycle(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _require_payload(payload)
    intc_id = _require_text(payload, "interceptor_id")
    intc_pos = _parse_vec3(payload.get("interceptor_position", [0.0, 0.0, 0.0]), field_name="interceptor_position")
    intc_vel = _parse_vec3(payload.get("interceptor_velocity", [0.0, 0.0, 0.0]), field_name="interceptor_velocity")
    tgt_pos = _parse_vec3(payload.get("target_position", [0.0, 0.0, 0.0]), field_name="target_position")
    tgt_vel = _parse_vec3(payload.get("target_velocity", [0.0, 0.0, 0.0]), field_name="target_velocity")
    try:
        solution = _manager.guide(intc_id, intc_pos, intc_vel, tgt_pos, tgt_vel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if solution is None:
        raise HTTPException(status_code=404, detail="No active interception")
    return solution.to_dict()


@router.get("/active")
async def active_interceptions() -> Dict[str, Any]:
    return {"interceptions": _manager.get_active_interceptions()}


@router.get("/result/{interceptor_id}")
async def get_result(interceptor_id: str) -> Dict[str, Any]:
    result = _manager.get_result(interceptor_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result.__dict__


@router.get("/stats")
async def stats() -> Dict[str, Any]:
    return _manager.get_stats()

