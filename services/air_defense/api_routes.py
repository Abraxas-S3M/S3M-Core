"""FastAPI routes for air-defense effector and zone orchestration.

Military context:
These endpoints expose controlled command-post functions for registering
effectors, managing layered coverage, and executing deterministic allocations.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from fastapi import APIRouter, HTTPException

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.models import (
    DefenseEchelon,
    DefenseZone,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
    EngagementEnvelope,
    TargetAllocation,
)
from services.air_defense.saudi_templates import build_saudi_air_defense_unit
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import DefenseZoneManager


router = APIRouter()
_REGISTRY = EffectorRegistry()
_ZONE_MANAGER = DefenseZoneManager()
_ALLOCATOR = TargetAllocator(registry=_REGISTRY, zone_manager=_ZONE_MANAGER)
_MISS_HANDLER = MissHandler(allocator=_ALLOCATOR, registry=_REGISTRY)


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _parse_enum(enum_type: Type[Enum], raw_value: Any, field_name: str) -> Enum:
    if isinstance(raw_value, enum_type):
        return raw_value
    text = str(raw_value).strip().lower()
    for member in enum_type:
        if member.value == text:
            return member
    raise HTTPException(status_code=400, detail=f"invalid {field_name}: {raw_value}")


def _parse_position(raw: Any) -> Tuple[float, float, float]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise HTTPException(status_code=400, detail="position must be [x_km, y_km, altitude_m]")
    return (float(raw[0]), float(raw[1]), float(raw[2]))


def _parse_effector(payload: Dict[str, Any]) -> Effector:
    envelope_data = payload.get("envelope") or {}
    state_data = payload.get("state") or {}
    try:
        envelope = EngagementEnvelope(
            min_range_km=float(envelope_data["min_range_km"]),
            max_range_km=float(envelope_data["max_range_km"]),
            min_altitude_m=float(envelope_data["min_altitude_m"]),
            max_altitude_m=float(envelope_data["max_altitude_m"]),
            azimuth_start_deg=float(envelope_data.get("azimuth_start_deg", 0.0)),
            azimuth_end_deg=float(envelope_data.get("azimuth_end_deg", 360.0)),
        )
        state = EffectorState(
            readiness=float(state_data.get("readiness", 1.0)),
            ammunition_current=int(state_data["ammunition_current"]),
            ammunition_capacity=int(state_data["ammunition_capacity"]),
            reload_time_seconds=float(state_data.get("reload_time_seconds", 0.0)),
            status=str(state_data.get("status", "ready")),
            queued_targets=int(state_data.get("queued_targets", 0)),
        )
        return Effector(
            effector_id=str(payload["effector_id"]),
            name_en=str(payload["name_en"]),
            name_ar=str(payload["name_ar"]),
            effector_type=_parse_enum(EffectorType, payload["effector_type"], "effector_type"),
            category=_parse_enum(EffectorCategory, payload["category"], "category"),
            echelon=_parse_enum(DefenseEchelon, payload["echelon"], "echelon"),
            envelope=envelope,
            state=state,
            zone_id=str(payload["zone_id"]),
            position=_parse_position(payload.get("position", (0.0, 0.0, 0.0))),
            priority=int(payload.get("priority", 100)),
            metadata=dict(payload.get("metadata", {})),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_zone(payload: Dict[str, Any]) -> DefenseZone:
    try:
        center = payload.get("center", (0.0, 0.0))
        if not isinstance(center, (tuple, list)) or len(center) != 2:
            raise ValueError("center must be [x_km, y_km]")
        return DefenseZone(
            zone_id=str(payload["zone_id"]),
            name_en=str(payload["name_en"]),
            name_ar=str(payload["name_ar"]),
            echelon=_parse_enum(DefenseEchelon, payload["echelon"], "echelon"),
            center=(float(center[0]), float(center[1])),
            min_radius_km=float(payload.get("min_radius_km", 0.0)),
            radius_km=float(payload["radius_km"]),
            min_altitude_m=float(payload.get("min_altitude_m", 0.0)),
            max_altitude_m=float(payload.get("max_altitude_m", 50000.0)),
            azimuth_start_deg=float(payload.get("azimuth_start_deg", 0.0)),
            azimuth_end_deg=float(payload.get("azimuth_end_deg", 360.0)),
            unit_id=str(payload.get("unit_id", "")),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_categories(values: Optional[Iterable[Any]]) -> Optional[List[EffectorCategory]]:
    if values is None:
        return None
    parsed = [_parse_enum(EffectorCategory, value, "category") for value in values]
    return parsed


@router.post("/air-defense/effectors/register")
async def register_effector(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register one typed effector channel."""
    effector = _parse_effector(payload)
    try:
        _REGISTRY.register_effector(effector, replace_existing=bool(payload.get("replace_existing", False)))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"effector": _serialize(effector)}


@router.delete("/air-defense/effectors/{effector_id}")
async def remove_effector(effector_id: str) -> Dict[str, Any]:
    """Remove one effector by ID."""
    removed = _REGISTRY.remove_effector(effector_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="effector not found")
    return {"removed": _serialize(removed)}


@router.get("/air-defense/effectors")
async def list_effectors(
    effector_type: Optional[str] = None,
    category: Optional[str] = None,
    echelon: Optional[str] = None,
    zone_id: Optional[str] = None,
    ready_only: bool = False,
) -> Dict[str, Any]:
    """List effectors with optional tactical filters."""
    filters: Dict[str, Any] = {}
    if effector_type:
        filters["effector_type"] = _parse_enum(EffectorType, effector_type, "effector_type")
    if category:
        filters["category"] = _parse_enum(EffectorCategory, category, "category")
    if echelon:
        filters["echelon"] = _parse_enum(DefenseEchelon, echelon, "echelon")
    if zone_id:
        filters["zone_id"] = zone_id
    filters["ready_only"] = bool(ready_only)
    effectors = _REGISTRY.query_effectors(**filters)
    return {"effectors": [_serialize(effector) for effector in effectors]}


@router.post("/air-defense/effectors/{effector_id}/ammunition")
async def update_effector_ammunition(effector_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update ammunition value for one effector."""
    if "ammunition_current" not in payload:
        raise HTTPException(status_code=400, detail="ammunition_current is required")
    try:
        effector = _REGISTRY.update_ammunition(effector_id, int(payload["ammunition_current"]))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"effector": _serialize(effector)}


@router.post("/air-defense/effectors/{effector_id}/readiness")
async def update_effector_readiness(effector_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update readiness score/status for one effector."""
    if "readiness" not in payload:
        raise HTTPException(status_code=400, detail="readiness is required")
    try:
        effector = _REGISTRY.set_readiness(
            effector_id,
            float(payload["readiness"]),
            status=payload.get("status"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"effector": _serialize(effector)}


@router.post("/air-defense/zones/register")
async def register_zone(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register one defense zone."""
    zone = _parse_zone(payload)
    try:
        _ZONE_MANAGER.register_zone(zone, replace_existing=bool(payload.get("replace_existing", False)))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"zone": _serialize(zone)}


@router.get("/air-defense/zones")
async def list_zones(echelon: Optional[str] = None, unit_id: Optional[str] = None) -> Dict[str, Any]:
    """List zones with optional echelon/unit filters."""
    parsed_echelon = _parse_enum(DefenseEchelon, echelon, "echelon") if echelon else None
    zones = _ZONE_MANAGER.list_zones(echelon=parsed_echelon, unit_id=unit_id)
    return {"zones": [_serialize(zone) for zone in zones]}


@router.post("/air-defense/allocate")
async def allocate_target(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Allocate best effector for one target."""
    try:
        result = _ALLOCATOR.allocate_target(
            target_id=str(payload["target_id"]),
            target_position=_parse_position(payload["target_position"]),
            target_type=str(payload.get("target_type", "unknown")),
            allowed_categories=_parse_categories(payload.get("allowed_categories")),
            preferred_categories=_parse_categories(payload.get("preferred_categories")),
            excluded_effector_ids=payload.get("excluded_effector_ids"),
            reserve_queue=bool(payload.get("reserve_queue", True)),
            fallback_depth=int(payload.get("fallback_depth", 0)),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"allocation_result": _serialize(result)}


@router.post("/air-defense/allocate/batch")
async def allocate_targets_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Allocate multiple targets in order."""
    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise HTTPException(status_code=400, detail="targets must be a list")
    try:
        results = _ALLOCATOR.allocate_many(targets)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": [_serialize(result) for result in results]}


@router.post("/air-defense/miss")
async def handle_miss(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle miss assessment and request automatic fallback allocation."""
    previous_raw = payload.get("previous_allocation")
    previous_allocation: Optional[TargetAllocation] = None
    if previous_raw:
        try:
            previous_allocation = TargetAllocation(
                allocation_id=str(previous_raw["allocation_id"]),
                target_id=str(previous_raw["target_id"]),
                target_type=str(previous_raw.get("target_type", "unknown")),
                target_position=_parse_position(previous_raw["target_position"]),
                assigned_effector_id=str(previous_raw["assigned_effector_id"]),
                echelon=_parse_enum(DefenseEchelon, previous_raw["echelon"], "echelon"),
                score=float(previous_raw.get("score", 0.0)),
                reason=str(previous_raw.get("reason", "prior allocation")),
                queued_index=int(previous_raw.get("queued_index", 0)),
                fallback_depth=int(previous_raw.get("fallback_depth", 0)),
                created_at=float(previous_raw.get("created_at", 0.0)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"invalid previous_allocation: missing {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid previous_allocation: {exc}") from exc

    try:
        result = _MISS_HANDLER.handle_miss(
            target_id=str(payload["target_id"]),
            target_position=_parse_position(payload["target_position"]),
            target_type=str(payload.get("target_type", "unknown")),
            previous_allocation=previous_allocation,
            miss_reason=str(payload.get("miss_reason", "unknown")),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"reallocation_result": _serialize(result)}


@router.post("/air-defense/templates/saudi/load")
async def load_saudi_template(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Load a Saudi-equivalent layered air-defense template into memory."""
    unit = build_saudi_air_defense_unit(
        unit_id=str(payload.get("unit_id", "saudi-ad-unit-1")),
        center=tuple(payload.get("center", (0.0, 0.0))),
        name_en=str(payload.get("name_en", "Saudi Layered Air Defense Unit")),
        name_ar=str(payload.get("name_ar", "Saudi Layered Air Defense Unit")),
    )
    for zone in unit.zones:
        _ZONE_MANAGER.register_zone(zone, replace_existing=True)
    for effector in unit.effectors:
        _REGISTRY.register_effector(effector, replace_existing=True)
    return {
        "unit_id": unit.unit_id,
        "zones_loaded": len(unit.zones),
        "effectors_loaded": len(unit.effectors),
    }


@router.get("/air-defense/status")
async def status() -> Dict[str, Any]:
    """Return operational status and loaded object counts."""
    return {
        "status": "operational",
        "effectors": len(_REGISTRY.list_effectors()),
        "zones": len(_ZONE_MANAGER.list_zones()),
    }
