"""FastAPI routes for radar adapter operations.

Military context:
These routes expose controlled command-post operations for managing a multi-
radar network and feeding a fused tactical air picture in offline deployments.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

from fastapi import APIRouter, HTTPException

from services.radar.krechet_radar_suite import load_krechet_suite
from services.radar.models import RadarBand, RadarConfig, RadarStatus, RadarType
from services.radar.radar_manager import RadarManager


router = APIRouter()
_RADAR_MANAGER = RadarManager()


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if hasattr(value, "to_dict"):
        return _serialize(value.to_dict())
    return value


def _parse_tuple3(raw: Any, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a [x, y, z] triple")
    return (float(raw[0]), float(raw[1]), float(raw[2]))


def _parse_probability_curve(raw: Any) -> Sequence[Tuple[float, float]]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="detection_probability_curve must be a list")
    curve = []
    for idx, pair in enumerate(raw):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise HTTPException(
                status_code=400,
                detail=f"detection_probability_curve[{idx}] must be [snr_db, probability]",
            )
        curve.append((float(pair[0]), float(pair[1])))
    return tuple(curve)


def _parse_radar_config(payload: Dict[str, Any]) -> RadarConfig:
    try:
        return RadarConfig(
            radar_id=str(payload["radar_id"]),
            radar_type=RadarType.from_value(payload["radar_type"]),
            radar_band=RadarBand.from_value(payload["radar_band"]),
            name_en=str(payload["name_en"]),
            name_ar=str(payload["name_ar"]),
            position_lla=_parse_tuple3(payload["position_lla"], "position_lla"),
            orientation_deg=_parse_tuple3(payload.get("orientation_deg", (0.0, 0.0, 0.0)), "orientation_deg"),
            scan_rate_hz=float(payload.get("scan_rate_hz", 1.0)),
            beam_width_az_deg=float(payload.get("beam_width_az_deg", 2.0)),
            beam_width_el_deg=float(payload.get("beam_width_el_deg", 4.0)),
            min_range_m=float(payload.get("min_range_m", 100.0)),
            max_range_m=float(payload.get("max_range_m", 120_000.0)),
            doppler_resolution_mps=float(payload.get("doppler_resolution_mps", 1.5)),
            nominal_detection_probability=float(payload.get("nominal_detection_probability", 0.9)),
            detection_probability_curve=_parse_probability_curve(payload.get("detection_probability_curve")),
            status=RadarStatus.from_value(payload.get("status", "ONLINE")),
            metadata=dict(payload.get("metadata", {})),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/radar/register")
async def register_radar(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register one radar channel for ingestion."""
    config = _parse_radar_config(payload)
    try:
        _RADAR_MANAGER.register_radar(config)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"radar": _serialize(config)}


@router.delete("/radar/{radar_id}")
async def unregister_radar(radar_id: str) -> Dict[str, Any]:
    """Remove one radar channel from ingestion."""
    removed = _RADAR_MANAGER.unregister_radar(radar_id)
    if not removed:
        raise HTTPException(status_code=404, detail="radar not found")
    return {"removed": radar_id}


@router.get("/radar")
async def list_radars() -> Dict[str, Any]:
    """List all registered radar configurations."""
    return {"radars": _RADAR_MANAGER.get_registered_radars()}


@router.post("/radar/{radar_id}/scan")
async def ingest_scan(radar_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ingest one raw radar scan and return normalized readings."""
    try:
        readings, correlations = _RADAR_MANAGER.ingest_scan_with_correlations(radar_id=radar_id, scan_input=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "radar_id": radar_id,
        "ingested_readings": [_serialize(reading) for reading in readings],
        "correlations": [_serialize(correlation) for correlation in correlations],
    }


@router.post("/radar/suites/krechet/load")
async def load_krechet(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load a Krechet-style multi-radar template into memory."""
    effective_payload = payload or {}
    origin = _parse_tuple3(effective_payload.get("origin_lla", (24.7136, 46.6753, 620.0)), "origin_lla")
    try:
        suite = load_krechet_suite(_RADAR_MANAGER, origin_lla=origin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "suite_name": suite.suite_name,
        "radars_loaded": len(suite.radar_configs),
        "radars": [_serialize(config) for config in suite.radar_configs],
    }


@router.post("/radar/fusion/process")
async def process_fusion() -> Dict[str, Any]:
    """Process pending radar readings through existing Layer 02 fusion."""
    tracks = _RADAR_MANAGER.process_fusion()
    return {"tracks": [_serialize(track) for track in tracks]}


@router.get("/radar/status")
async def radar_status() -> Dict[str, Any]:
    """Return subsystem operational status for command health dashboards."""
    return _RADAR_MANAGER.get_status()
