"""Pydantic models for S3M Phase 15 sensor analytics API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class ProcessSARRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096)
    confidence_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class SARDetectionResponse(BaseModel):
    detection_id: str
    image_id: str
    bbox: Tuple[float, float, float, float]
    geo_position: Tuple[float, float]
    confidence: float
    class_name: str
    estimated_length_meters: float
    estimated_width_meters: float
    heading_deg: Optional[float] = None
    speed_knots: Optional[float] = None
    model_used: str
    timestamp: str
    model_not_loaded: Optional[bool] = None


class IngestAISRequest(BaseModel):
    filepath: str = Field(..., min_length=1, max_length=4096)


class AISVesselResponse(BaseModel):
    mmsi: str
    vessel_name: str
    classification: str
    flag_state: str
    imo_number: Optional[str] = None
    length_meters: float
    beam_meters: float
    last_position: Tuple[float, float]
    last_speed_knots: float
    last_heading_deg: float
    last_seen: str
    positions_count: int
    ais_active: bool
    risk_score: float
    track: List[Dict[str, Any]]


class AISVesselListResponse(BaseModel):
    vessels: List[AISVesselResponse]
    total: int


class BorderAlertResponse(BaseModel):
    alert_id: str
    zone_id: str
    timestamp: str
    alert_type: str
    severity: str
    position: Tuple[float, float]
    description: str
    vessel_id: Optional[str] = None
    confidence: float
    evidence: List[Dict[str, Any]]


class BorderScanResponse(BaseModel):
    alerts_by_zone: Dict[str, List[BorderAlertResponse]]
    total_alerts: int
    zones_scanned: int


class ZoneCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    zone_type: str = Field(..., min_length=1, max_length=64)
    polygon: List[Tuple[float, float]] = Field(..., min_length=3)
    threat_level: str = Field(default="low", min_length=1, max_length=16)


class ZoneResponse(BaseModel):
    zone_id: str
    name: str
    zone_type: str
    polygon: List[Tuple[float, float]]
    threat_level: str
    active_sensors: List[str]


class ZoneStatusResponse(BaseModel):
    zones: List[ZoneResponse]
    total: int


class MaritimePictureResponse(BaseModel):
    timestamp: str
    region: str
    vessels: List[Dict[str, Any]]
    sar_detections: List[Dict[str, Any]]
    border_alerts: List[Dict[str, Any]]
    zones: List[Dict[str, Any]]
    statistics: Dict[str, Any]


class DarkVesselResponse(BaseModel):
    vessels: List[Dict[str, Any]]
    total: int


class SensorAnalyticsStatusResponse(BaseModel):
    fusion: Dict[str, Any]
    datasets: Dict[str, Any]


class VesselQueryParams(BaseModel):
    classification: Optional[str] = None
    zone_id: Optional[str] = None
    dark_only: bool = False
    limit: int = Field(default=100, ge=1, le=5000)
