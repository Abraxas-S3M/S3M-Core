"""FastAPI routes for radar management and integration.

Military context:
These endpoints support tactical radar registration, scan ingestion, and
multi-sensor track fusion for an offline command-post air picture.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from fastapi import APIRouter, HTTPException

from services.radar.krechet_radar_suite import create_krechet_radar_suite
from services.radar.models import RadarBand, RadarConfig, RadarType, ScanMode
from services.radar.radar_manager import RadarManager

router = APIRouter(prefix="/radar", tags=["radar"])

_manager = RadarManager()


def _parse_xyz(raw_value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(raw_value, (tuple, list)) or len(raw_value) != 3:
        raise HTTPException(status_code=400, detail=f"{field_name} must be [x_m, y_m, z_m]")
    try:
        return (float(raw_value[0]), float(raw_value[1]), float(raw_value[2]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must contain numeric coordinates") from exc


@router.get("/radars")
async def list_radars() -> Dict[str, Any]:
    radars = _manager.list_radars()
    return {"radars": [r.to_dict() for r in radars], "count": len(radars)}


@router.get("/radars/{radar_id}")
async def get_radar(radar_id: str) -> Dict[str, Any]:
    r = _manager.get_radar(radar_id)
    if not r:
        raise HTTPException(status_code=404, detail="Radar not found")
    return r.to_dict()


@router.get("/radars/{radar_id}/status")
async def get_radar_status(radar_id: str) -> Dict[str, Any]:
    s = _manager.get_status(radar_id)
    if not s:
        raise HTTPException(status_code=404, detail="Radar not found")
    return {
        "radar_id": s.radar_id,
        "operational": s.operational,
        "scans_received": s.scans_received,
        "plots_received": s.plots_received,
        "plots_correlated": s.plots_correlated,
        "last_scan": s.last_scan_time.isoformat() if s.last_scan_time else None,
    }


@router.post("/radars/register")
async def register_radar(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        config = RadarConfig(
            name_en=str(payload.get("name_en", "Radar")),
            name_ar=str(payload.get("name_ar", "رادار")),
            radar_type=RadarType(str(payload.get("radar_type", "generic_3d"))),
            band=RadarBand(str(payload.get("band", "X"))),
            position=_parse_xyz(payload.get("position", [0.0, 0.0, 0.0]), field_name="position"),
            max_range_m=float(payload.get("max_range_m", 50000.0)),
            scan_mode=ScanMode(str(payload.get("scan_mode", "volume"))),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    registered = _manager.register_radar(config)
    return {"radar_id": registered.radar_id, "status": "registered"}


@router.post("/radars/{radar_id}/scan")
async def ingest_scan(radar_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ingest a radar scan and process through the full pipeline."""
    try:
        plots = _manager.ingest_scan(radar_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "plots_processed": len(plots),
        "classified": sum(1 for p in plots if p.rcs_classification.value != "unknown"),
        "correlated": sum(1 for p in plots if p.correlated_track_id),
        # Limit response size to keep tactical links responsive under load.
        "plots": [p.to_dict() for p in plots[:20]],
    }


@router.post("/radars/fuse")
async def trigger_fusion() -> Dict[str, Any]:
    """Trigger sensor fusion across all radar inputs."""
    tracks = _manager.process_fused_tracks()
    return {
        "tracks": len(tracks),
        "confirmed": sum(1 for t in tracks if t.state.value == "confirmed"),
    }


@router.get("/stats")
async def radar_stats() -> Dict[str, Any]:
    return _manager.get_stats()


@router.get("/status")
async def all_radar_status() -> Dict[str, Any]:
    return _manager.get_all_status()


@router.post("/setup/krechet-suite")
async def setup_krechet_suite(payload: Dict[str, Any]) -> Dict[str, Any]:
    center = _parse_xyz(payload.get("center", [0.0, 0.0, 0.0]), field_name="center")
    try:
        configs = create_krechet_radar_suite(_manager, center)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "radars_created": len(configs),
        "radars": [c.to_dict() for c in configs],
        "stats": _manager.get_stats(),
    }

