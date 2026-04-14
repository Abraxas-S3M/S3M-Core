"""FastAPI routes for predictive-defense trajectory-to-action workflows.

Military context:
These endpoints expose local command-post control of predictive cueing without
external dependencies, suitable for air-gapped defense operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from services.predictive_defense.preposition_optimizer import InterceptorProfile
from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager

router = APIRouter(prefix="/predictive-defense", tags=["predictive-defense"])
_MANAGER = PredictiveDefenseManager()


@dataclass
class _ApiTrack:
    track_id: str
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    classification: str = "unknown"
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _parse_vec3(raw: Any, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise HTTPException(status_code=400, detail=f"{field_name} must be [x_m, y_m, z_m]")
    try:
        return (float(raw[0]), float(raw[1]), float(raw[2]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must contain numeric values") from exc


def _parse_tracks(raw_tracks: Any) -> List[_ApiTrack]:
    if not isinstance(raw_tracks, list):
        raise HTTPException(status_code=400, detail="tracks must be a list")
    parsed: List[_ApiTrack] = []
    for idx, raw in enumerate(raw_tracks):
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail=f"tracks[{idx}] must be an object")
        track_id = str(raw.get("track_id", "")).strip()
        if not track_id:
            raise HTTPException(status_code=400, detail=f"tracks[{idx}].track_id is required")
        parsed.append(
            _ApiTrack(
                track_id=track_id,
                position=_parse_vec3(raw.get("position", [0.0, 0.0, 0.0]), f"tracks[{idx}].position"),
                velocity=_parse_vec3(raw.get("velocity", [0.0, 0.0, 0.0]), f"tracks[{idx}].velocity"),
                classification=str(raw.get("classification", "unknown")),
                confidence=float(raw.get("confidence", 0.5)),
                metadata=dict(raw.get("metadata", {})),
            )
        )
    return parsed


@router.get("/status")
async def status() -> Dict[str, Any]:
    posture = _MANAGER.get_last_posture()
    return {
        "status": "operational",
        "stats": _MANAGER.get_stats(),
        "last_posture_level": posture.posture_level if posture else None,
    }


@router.post("/defended-asset")
async def update_defended_asset(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        position = _parse_vec3(payload["position_m"], "position_m")
        _MANAGER.update_defended_asset(
            position_m=position,
            name_en=payload.get("name_en"),
            name_ar=payload.get("name_ar"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}") from exc
    return {"status": "updated"}


@router.post("/interceptors/configure")
async def configure_interceptors(payload: Dict[str, Any]) -> Dict[str, Any]:
    profiles_raw = payload.get("profiles")
    if not isinstance(profiles_raw, list):
        raise HTTPException(status_code=400, detail="profiles must be a list")
    profiles: List[InterceptorProfile] = []
    for idx, profile_raw in enumerate(profiles_raw):
        if not isinstance(profile_raw, dict):
            raise HTTPException(status_code=400, detail=f"profiles[{idx}] must be an object")
        try:
            profiles.append(
                InterceptorProfile(
                    interceptor_id=str(profile_raw["interceptor_id"]),
                    position_m=_parse_vec3(profile_raw["position_m"], f"profiles[{idx}].position_m"),
                    max_speed_mps=float(profile_raw["max_speed_mps"]),
                    readiness=float(profile_raw.get("readiness", 1.0)),
                )
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field in profiles[{idx}]: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid profile {idx}: {exc}") from exc
    _MANAGER.configure_interceptors(profiles)
    return {"configured": len(profiles)}


@router.post("/run-cycle")
async def run_cycle(payload: Dict[str, Any]) -> Dict[str, Any]:
    tracks: Optional[List[_ApiTrack]] = None
    if "tracks" in payload:
        tracks = _parse_tracks(payload["tracks"])
    posture = _MANAGER.process_cycle(tracks=tracks)
    return posture.to_dict()


@router.get("/posture")
async def get_posture() -> Dict[str, Any]:
    posture = _MANAGER.get_last_posture()
    if posture is None:
        raise HTTPException(status_code=404, detail="No posture has been computed yet")
    return posture.to_dict()
