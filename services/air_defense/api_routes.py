"""FastAPI routes for air defense effector and zone management.

Military context:
Exposes C2 endpoints for managing effectors, defense zones, and target
allocation — the operator-facing API for Krechet-equivalent air defense.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple, Type, TypeVar

from fastapi import APIRouter, HTTPException

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.models import DefenseEchelon, EffectorCategory, EffectorState
from services.air_defense.saudi_templates import create_krechet_equivalent_unit
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import ZoneManager

router = APIRouter(prefix="/air-defense", tags=["air_defense"])

# Singleton instances
_registry = EffectorRegistry()
_zone_mgr = ZoneManager()
_allocator = TargetAllocator(_registry, _zone_mgr)
_miss_handler = MissHandler(_registry, _allocator)

E = TypeVar("E")


def _parse_enum(value: Optional[str], enum_cls: Type[E], field_name: str) -> Optional[E]:
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid {field_name}: {value}") from exc


def _parse_position(value: Any, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a 3-element list [x,y,z]")
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} contains non-numeric values") from exc


def _parse_float(value: Any, field_name: str, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be numeric") from exc


@router.get("/effectors")
async def list_effectors(
    category: Optional[str] = None,
    echelon: Optional[str] = None,
    available_only: bool = False,
) -> Dict[str, Any]:
    """List all registered effectors with optional filters."""
    kwargs: Dict[str, Any] = {"available_only": available_only}
    parsed_category = _parse_enum(category, EffectorCategory, "category")
    parsed_echelon = _parse_enum(echelon, DefenseEchelon, "echelon")
    if parsed_category is not None:
        kwargs["category"] = parsed_category
    if parsed_echelon is not None:
        kwargs["echelon"] = parsed_echelon
    effectors = _registry.query(**kwargs)
    return {"effectors": [e.to_dict() for e in effectors], "count": len(effectors)}


@router.get("/effectors/{effector_id}")
async def get_effector(effector_id: str) -> Dict[str, Any]:
    eff = _registry.get(effector_id)
    if not eff:
        raise HTTPException(status_code=404, detail="Effector not found")
    return eff.to_dict()


@router.post("/effectors/{effector_id}/state")
async def update_effector_state(effector_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state_value = payload.get("state", "ready")
    new_state = _parse_enum(str(state_value), EffectorState, "state")
    if new_state is None:
        raise HTTPException(status_code=400, detail="state required")
    if not _registry.update_state(effector_id, new_state):
        raise HTTPException(status_code=404, detail="Effector not found")
    return {"effector_id": effector_id, "state": new_state.value}


@router.post("/effectors/{effector_id}/resupply")
async def resupply_effector(effector_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    rounds_raw = payload.get("rounds")
    rounds = None
    if rounds_raw is not None:
        if isinstance(rounds_raw, bool):
            raise HTTPException(status_code=400, detail="rounds must be an integer")
        try:
            rounds = int(rounds_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="rounds must be an integer") from exc
        if rounds < 0:
            raise HTTPException(status_code=400, detail="rounds must be >= 0")
    if not _registry.resupply(effector_id, rounds):
        raise HTTPException(status_code=404, detail="Effector not found")
    eff = _registry.get(effector_id)
    return {"effector_id": effector_id, "ammunition_remaining": eff.ammunition_remaining if eff else 0}


@router.get("/effectors/stats/summary")
async def effector_stats() -> Dict[str, Any]:
    return _registry.get_stats()


@router.get("/zones")
async def list_zones(echelon: Optional[str] = None) -> Dict[str, Any]:
    ech = _parse_enum(echelon, DefenseEchelon, "echelon")
    zones = _zone_mgr.list_zones(echelon=ech)
    return {"zones": [z.to_dict() for z in zones], "count": len(zones)}


@router.get("/zones/coverage")
async def zone_coverage() -> Dict[str, Any]:
    return _zone_mgr.get_coverage_report()


@router.post("/allocate")
async def allocate_target(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Allocate a target to the best available effector."""
    target_id = str(payload.get("target_id", "")).strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="target_id required")
    position = _parse_position(payload.get("position", [0, 0, 0]), "position")
    speed = _parse_float(payload.get("speed_mps", 0.0), "speed_mps", default=0.0)
    classification = str(payload.get("classification", "UNKNOWN")).strip() or "UNKNOWN"
    result = _allocator.allocate(target_id, position, speed, classification)
    return {
        "allocated": result.allocated,
        "allocation": result.allocation.to_dict() if result.allocation else None,
        "alternatives": result.alternatives_count,
        "echelon": result.echelon_used.value if result.echelon_used else None,
        "reasoning": result.reasoning,
    }


@router.post("/miss")
async def report_miss(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Report an engagement miss and trigger re-allocation."""
    alloc_id = str(payload.get("allocation_id", "")).strip()
    if not alloc_id:
        raise HTTPException(status_code=400, detail="allocation_id required")
    log = _allocator.get_allocation_log(limit=1000)
    alloc = next((a for a in log if a.allocation_id == alloc_id), None)
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")
    new_pos = _parse_position(payload["updated_position"], "updated_position") if "updated_position" in payload else None
    new_speed = _parse_float(payload.get("updated_speed"), "updated_speed") if "updated_speed" in payload else None
    result = _miss_handler.report_miss(alloc, new_pos, new_speed)
    return {
        "reallocated": result.allocated,
        "allocation": result.allocation.to_dict() if result.allocation else None,
        "reasoning": result.reasoning,
    }


@router.post("/kill")
async def report_kill(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Report a confirmed kill."""
    alloc_id = str(payload.get("allocation_id", "")).strip()
    if not alloc_id:
        raise HTTPException(status_code=400, detail="allocation_id required")
    log = _allocator.get_allocation_log(limit=1000)
    alloc = next((a for a in log if a.allocation_id == alloc_id), None)
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")
    _miss_handler.report_kill(alloc)
    return {"status": "kill_confirmed", "allocation_id": alloc_id}


@router.post("/setup/krechet-unit")
async def setup_krechet_unit(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a full Krechet-equivalent air defense unit."""
    center = _parse_position(payload.get("center", [0, 0, 0]), "center")
    asset = str(payload.get("defended_asset", "Critical Infrastructure"))
    asset_ar = str(payload.get("defended_asset_ar", "البنية التحتية الحيوية"))
    unit = create_krechet_equivalent_unit(_registry, _zone_mgr, center, asset, asset_ar)
    return {
        "unit_id": unit.unit_id,
        "name_en": unit.name_en,
        "effectors": len(unit.effector_ids),
        "zones": len(unit.zone_ids),
        "registry_stats": _registry.get_stats(),
        "coverage": _zone_mgr.get_coverage_report(),
    }


@router.get("/allocation-log")
async def allocation_log(limit: int = 50) -> Dict[str, Any]:
    log = _allocator.get_allocation_log(limit)
    return {"entries": [a.to_dict() for a in log], "count": len(log)}


@router.get("/miss-log")
async def miss_log(limit: int = 100) -> Dict[str, Any]:
    return {"entries": _miss_handler.get_miss_log(limit), "stats": _miss_handler.get_miss_stats()}

