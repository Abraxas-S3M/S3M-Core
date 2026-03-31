"""Pydantic request/response models for Phase 5 API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class IngestSuricataRequest(BaseModel):
    filepath: str = Field(..., min_length=1, max_length=4096)


class IngestWazuhRequest(BaseModel):
    filepath: str = Field(..., min_length=1, max_length=4096)


class IngestImageRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096)
    location: Optional[Dict[str, Any]] = None


class IngestTelemetryRequest(BaseModel):
    data: List[List[float]] = Field(..., min_length=1)
    feature_names: Optional[List[str]] = None


class IngestManualRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: str = Field(..., min_length=1, max_length=4096)
    level: str = Field(..., min_length=1, max_length=32)
    category: str = Field(..., min_length=1, max_length=64)


class ThreatEventResponse(BaseModel):
    event_id: str
    timestamp: str
    source: str
    level: str
    category: str
    title: str
    description: str
    raw_data: Dict[str, Any]
    confidence: float
    location: Optional[Dict[str, Any]] = None
    asset_ids: List[str]
    recommended_action: Optional[str] = None
    llm_assessment: Optional[str] = None
    classification: str


class DetectionResultResponse(BaseModel):
    source: str
    processing_time_ms: float
    total_events: int
    events_by_level: Dict[str, int]
    events: List[ThreatEventResponse]


class ThreatListResponse(BaseModel):
    events: List[ThreatEventResponse]
    total: int


class ThreatDetailResponse(BaseModel):
    event: ThreatEventResponse


class AssessThreatResponse(BaseModel):
    event: ThreatEventResponse
    assessment: Optional[str] = None


class ThreatStatsResponse(BaseModel):
    total_events: int
    events_by_level: Dict[str, int]
    events_by_source: Dict[str, int]
    events_by_category: Dict[str, int]
    last_event_timestamp: Optional[str] = None


class SitrepResponse(BaseModel):
    sitrep: str


class RegisterSensorRequest(BaseModel):
    sensor_id: str = Field(..., min_length=1, max_length=128)
    sensor_type: str = Field(..., min_length=1, max_length=64)
    config: Optional[Dict[str, Any]] = None


class IngestSensorRequest(BaseModel):
    sensor_id: str = Field(..., min_length=1, max_length=128)
    data: Dict[str, Any]
    position: Optional[Tuple[float, float, float]] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SensorReadingResponse(BaseModel):
    sensor_id: str
    sensor_type: str
    timestamp: str
    data: Dict[str, Any]
    position: Optional[Tuple[float, float, float]] = None
    confidence: float


class TrackResponse(BaseModel):
    track_id: str
    state: str
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    covariance: List[List[float]]
    last_update: str
    sensor_sources: List[str]
    classification: Optional[str] = None
    confidence: float
    history: List[Dict[str, Any]]


class SensorListResponse(BaseModel):
    sensors: List[Dict[str, Any]]
    total: int


class TrackListResponse(BaseModel):
    tracks: List[TrackResponse]
    total: int
