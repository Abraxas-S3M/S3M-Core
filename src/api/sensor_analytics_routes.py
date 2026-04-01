"""FastAPI routes for S3M Layer 09 Sensor & Remote Sensing Analytics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.sensor_analytics import BorderZone, SensorAnalyticsManager, VesselClassification
from src.api.sensor_analytics_models import (
    AISVesselListResponse,
    AISVesselResponse,
    BorderAlertResponse,
    BorderScanResponse,
    DarkVesselResponse,
    IngestAISRequest,
    MaritimePictureResponse,
    ProcessSARRequest,
    SensorAnalyticsStatusResponse,
    VesselQueryParams,
    ZoneCreateRequest,
    ZoneResponse,
    ZoneStatusResponse,
)

sensor_analytics_router = APIRouter()
_manager = SensorAnalyticsManager()


def _as_picture_response() -> MaritimePictureResponse:
    picture = _manager.get_maritime_picture()
    return MaritimePictureResponse(**picture.to_dict())


@sensor_analytics_router.post("/sensor-analytics/sar/detect")
async def process_sar(req: ProcessSARRequest) -> Dict[str, Any]:
    try:
        result = _manager.process_sar(req.image_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = {
        "detections": int(result.get("detections", 0)),
        "matched": int(result.get("matched", 0)),
        "dark_vessels": int(result.get("dark_vessels", 0)),
        "alerts": int(result.get("alerts", 0)),
        "items": [det.to_dict() for det in _manager.fusion.latest_unmatched_sar],
    }
    return payload


@sensor_analytics_router.get("/sensor-analytics/sar/model")
async def sar_model_info() -> Dict[str, Any]:
    return _manager.fusion.sar_detector.get_model_info()


@sensor_analytics_router.post("/sensor-analytics/ais/ingest")
async def ingest_ais(req: IngestAISRequest) -> Dict[str, Any]:
    try:
        return _manager.ingest_ais(req.filepath)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@sensor_analytics_router.get("/sensor-analytics/ais/vessels", response_model=AISVesselListResponse)
async def list_ais_vessels(
    classification: Optional[str] = Query(default=None),
    zone_id: Optional[str] = Query(default=None),
    dark_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=5000),
) -> AISVesselListResponse:
    _ = VesselQueryParams(
        classification=classification,
        zone_id=zone_id,
        dark_only=dark_only,
        limit=limit,
    )
    if zone_id:
        zone = _manager.fusion.border_engine.zone_manager.get_zone(zone_id)
        if zone is None:
            raise HTTPException(status_code=404, detail=f"Unknown zone: {zone_id}")
        vessels = _manager.fusion.ais_tracker.get_vessels_in_zone(zone)
    else:
        vessels = _manager.fusion.ais_tracker.get_all_vessels()
    if classification:
        try:
            enum_value = VesselClassification[classification.upper()]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid classification: {classification}") from exc
        vessels = [v for v in vessels if v.classification == enum_value]
    if dark_only:
        vessels = [v for v in vessels if v.is_dark()]
    vessels = vessels[:limit]
    return AISVesselListResponse(
        vessels=[AISVesselResponse(**v.to_dict()) for v in vessels],
        total=len(vessels),
    )


@sensor_analytics_router.get("/sensor-analytics/ais/vessels/{mmsi}", response_model=AISVesselResponse)
async def vessel_detail(mmsi: str) -> AISVesselResponse:
    vessel = _manager.fusion.ais_tracker.get_vessel(mmsi)
    if vessel is None:
        raise HTTPException(status_code=404, detail=f"Vessel not found: {mmsi}")
    return AISVesselResponse(**vessel.to_dict())


@sensor_analytics_router.get("/sensor-analytics/ais/dark", response_model=DarkVesselResponse)
async def dark_vessels() -> DarkVesselResponse:
    dark = _manager.get_dark_vessels()
    return DarkVesselResponse(vessels=dark, total=len(dark))


@sensor_analytics_router.post("/sensor-analytics/border/scan", response_model=BorderScanResponse)
async def border_scan() -> BorderScanResponse:
    try:
        scanned = _manager.scan_borders()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    alerts_by_zone = {
        zone_id: [BorderAlertResponse(**alert) for alert in alerts]
        for zone_id, alerts in scanned.items()
    }
    total = sum(len(items) for items in alerts_by_zone.values())
    return BorderScanResponse(
        alerts_by_zone=alerts_by_zone,
        total_alerts=total,
        zones_scanned=len(scanned),
    )


@sensor_analytics_router.get("/sensor-analytics/border/zones", response_model=List[ZoneResponse])
async def list_zones() -> List[ZoneResponse]:
    return [
        ZoneResponse(**z.to_dict())
        for z in _manager.fusion.border_engine.zone_manager.get_zones()
    ]


@sensor_analytics_router.post("/sensor-analytics/border/zones", response_model=ZoneResponse)
async def create_or_update_zone(req: ZoneCreateRequest) -> ZoneResponse:
    zone_id = f"ZONE-CUSTOM-{abs(hash(req.name)) % 100000}"
    zone = BorderZone(
        zone_id=zone_id,
        name=req.name,
        zone_type=req.zone_type,
        polygon=[tuple(v) for v in req.polygon],
        threat_level=req.threat_level,
        active_sensors=["ais", "sentinel-1"],
    )
    manager = _manager.fusion.border_engine.zone_manager
    existing = manager.get_zone(zone_id)
    if existing is None:
        manager.zones.append(zone)
    else:
        existing.name = zone.name
        existing.zone_type = zone.zone_type
        existing.polygon = zone.polygon
        existing.threat_level = zone.threat_level
    _manager.fusion.ais_anomaly.set_restricted_zones(manager.get_zones())
    return ZoneResponse(**zone.to_dict())


@sensor_analytics_router.get("/sensor-analytics/border/alerts", response_model=List[BorderAlertResponse])
async def list_alerts(
    zone_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
) -> List[BorderAlertResponse]:
    alerts = [a.to_dict() for a in _manager.fusion.border_engine.active_alerts]
    if zone_id:
        alerts = [a for a in alerts if a.get("zone_id") == zone_id]
    if severity:
        alerts = [a for a in alerts if str(a.get("severity", "")).lower() == severity.lower()]
    return [BorderAlertResponse(**a) for a in alerts]


@sensor_analytics_router.get("/sensor-analytics/maritime/picture", response_model=MaritimePictureResponse)
async def maritime_picture() -> MaritimePictureResponse:
    return _as_picture_response()


@sensor_analytics_router.get("/sensor-analytics/maritime/stats")
async def maritime_stats() -> Dict[str, Any]:
    return _manager.get_statistics()


@sensor_analytics_router.post("/sensor-analytics/maritime/export")
async def export_maritime_picture(payload: Dict[str, Any]) -> Dict[str, Any]:
    filepath = str(payload.get("filepath", "data/sensor-analytics/maritime_picture.geojson"))
    file_format = str(payload.get("format", "geojson"))
    try:
        _manager.fusion.export_picture(filepath, format=file_format)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "exported", "filepath": filepath, "format": file_format}


@sensor_analytics_router.get("/sensor-analytics/status", response_model=SensorAnalyticsStatusResponse)
async def sensor_analytics_status() -> SensorAnalyticsStatusResponse:
    status = _manager.health_check()
    return SensorAnalyticsStatusResponse(**status)


@sensor_analytics_router.get("/sensor-analytics/datasets")
async def list_datasets() -> Dict[str, Any]:
    datasets = _manager.datasets.list_datasets()
    return {"datasets": datasets, "total": len(datasets)}
