"""FastAPI routes for S3M Phase 5 threat detection and sensor fusion."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.threat_models import (
    AssessThreatResponse,
    DetectionResultResponse,
    IngestImageRequest,
    IngestManualRequest,
    IngestSensorRequest,
    IngestSuricataRequest,
    IngestTelemetryRequest,
    IngestWazuhRequest,
    RegisterSensorRequest,
    SensorListResponse,
    SensorReadingResponse,
    SitrepResponse,
    ThreatDetailResponse,
    ThreatEventResponse,
    ThreatListResponse,
    ThreatStatsResponse,
    TrackListResponse,
    TrackResponse,
)
from src.sensor_fusion.models import SensorType
from src.sensor_fusion.sensor_manager import SensorManager
from src.threat_detection.models import ThreatEvent
from src.threat_detection.threat_manager import ThreatManager

threat_router = APIRouter()
sensor_router = APIRouter()

_threat_manager = ThreatManager()
_sensor_manager = SensorManager()

_audit_log: List[Dict[str, Any]] = []


def _audit(action: str, details: Dict[str, Any]) -> None:
    entry = {"action": action, "details": details}
    _audit_log.append(entry)
    if len(_audit_log) > 1000:
        del _audit_log[:-1000]


def _event_to_response(event: ThreatEvent) -> ThreatEventResponse:
    return ThreatEventResponse(**event.to_dict())


@threat_router.post("/threats/ingest/suricata", response_model=DetectionResultResponse)
async def ingest_suricata(req: IngestSuricataRequest) -> DetectionResultResponse:
    try:
        result = _threat_manager.ingest_suricata_log(req.filepath)
    except Exception as exc:
        _audit("threat_ingest_suricata_error", {"filepath": req.filepath, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("threat_ingest_suricata", {"filepath": req.filepath, "events": result.total_events})
    return DetectionResultResponse(**result.to_dict())


@threat_router.post("/threats/ingest/wazuh", response_model=DetectionResultResponse)
async def ingest_wazuh(req: IngestWazuhRequest) -> DetectionResultResponse:
    try:
        result = _threat_manager.ingest_wazuh_alerts(req.filepath)
    except Exception as exc:
        _audit("threat_ingest_wazuh_error", {"filepath": req.filepath, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("threat_ingest_wazuh", {"filepath": req.filepath, "events": result.total_events})
    return DetectionResultResponse(**result.to_dict())


@threat_router.post("/threats/ingest/image", response_model=DetectionResultResponse)
async def ingest_image(req: IngestImageRequest) -> DetectionResultResponse:
    try:
        result = _threat_manager.ingest_image(req.image_path, location=req.location)
    except Exception as exc:
        _audit("threat_ingest_image_error", {"image_path": req.image_path, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("threat_ingest_image", {"image_path": req.image_path, "events": result.total_events})
    return DetectionResultResponse(**result.to_dict())


@threat_router.post("/threats/ingest/telemetry", response_model=DetectionResultResponse)
async def ingest_telemetry(req: IngestTelemetryRequest) -> DetectionResultResponse:
    try:
        result = _threat_manager.ingest_telemetry(req.data, feature_names=req.feature_names)
    except Exception as exc:
        _audit("threat_ingest_telemetry_error", {"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("threat_ingest_telemetry", {"events": result.total_events})
    return DetectionResultResponse(**result.to_dict())


@threat_router.post("/threats/ingest/manual", response_model=ThreatDetailResponse)
async def ingest_manual(req: IngestManualRequest) -> ThreatDetailResponse:
    try:
        event = _threat_manager.ingest_manual(
            title=req.title,
            description=req.description,
            level=req.level,
            category=req.category,
        )
    except Exception as exc:
        _audit("threat_ingest_manual_error", {"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("threat_ingest_manual", {"event_id": event.event_id, "level": event.level.name})
    return ThreatDetailResponse(event=_event_to_response(event))


@threat_router.get("/threats", response_model=ThreatListResponse)
async def get_threats(
    level: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> ThreatListResponse:
    try:
        events = _threat_manager.get_threats(level=level, source=source, category=category, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ThreatListResponse(events=[_event_to_response(e) for e in events], total=len(events))


@threat_router.get("/threats/stats", response_model=ThreatStatsResponse)
async def get_threat_stats() -> ThreatStatsResponse:
    stats = _threat_manager.get_stats()
    return ThreatStatsResponse(**stats)


@threat_router.get("/threats/sitrep", response_model=SitrepResponse)
async def get_sitrep() -> SitrepResponse:
    sitrep = _threat_manager.generate_sitrep()
    _audit("threat_sitrep", {"length": len(sitrep)})
    return SitrepResponse(sitrep=sitrep)


@threat_router.get("/threats/{event_id}", response_model=ThreatDetailResponse)
async def get_threat_detail(event_id: str) -> ThreatDetailResponse:
    if not isinstance(event_id, str) or not event_id.strip():
        raise HTTPException(status_code=400, detail="event_id must be a non-empty string")
    events = _threat_manager.get_threats(limit=10000)
    for event in events:
        if event.event_id == event_id:
            return ThreatDetailResponse(event=_event_to_response(event))
    raise HTTPException(status_code=404, detail=f"Threat event not found: {event_id}")


@threat_router.post("/threats/{event_id}/assess", response_model=AssessThreatResponse)
async def assess_threat(event_id: str) -> AssessThreatResponse:
    try:
        event = _threat_manager.assess_threat(event_id)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("threat_assess", {"event_id": event_id})
    return AssessThreatResponse(event=_event_to_response(event), assessment=event.llm_assessment)


@sensor_router.get("/sensors", response_model=SensorListResponse)
async def list_sensors() -> SensorListResponse:
    sensors = _sensor_manager.get_sensors()
    return SensorListResponse(sensors=sensors, total=len(sensors))


@sensor_router.get("/sensors/tracks", response_model=TrackListResponse)
async def list_tracks() -> TrackListResponse:
    tracks = _sensor_manager.get_fused_tracks()
    payload = [TrackResponse(**track.to_dict()) for track in tracks]
    return TrackListResponse(tracks=payload, total=len(payload))


@sensor_router.post("/sensors/register")
async def register_sensor(req: RegisterSensorRequest) -> Dict[str, Any]:
    try:
        _sensor_manager.register_sensor(
            sensor_id=req.sensor_id,
            sensor_type=SensorType.from_value(req.sensor_type),
            config=req.config,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("sensor_register", {"sensor_id": req.sensor_id, "sensor_type": req.sensor_type})
    return {"status": "registered", "sensor_id": req.sensor_id}


@sensor_router.post("/sensors/ingest")
async def ingest_sensor(req: IngestSensorRequest) -> Dict[str, Any]:
    try:
        reading = _sensor_manager.ingest(
            sensor_id=req.sensor_id,
            data=req.data,
            position=tuple(req.position) if req.position else None,
            confidence=req.confidence,
        )
        tracks = _sensor_manager.process()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("sensor_ingest", {"sensor_id": req.sensor_id, "tracks": len(tracks)})
    reading_payload = SensorReadingResponse(
        sensor_id=reading.sensor_id,
        sensor_type=reading.sensor_type.value,
        timestamp=reading.timestamp.isoformat(),
        data=reading.data,
        position=reading.position,
        confidence=reading.confidence,
    )
    return {"reading": reading_payload.model_dump(), "tracks": [track.to_dict() for track in tracks]}
