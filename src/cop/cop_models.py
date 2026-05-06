"""Pydantic models for the Saudi MOD COP backend service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CopTheater(BaseModel):
    """Theater metadata used to frame COP data for operators."""

    track: str
    name: str
    center: List[float] = Field(min_length=2, max_length=2)
    bounds: List[List[float]] = Field(min_length=2, max_length=2)
    focus_areas: List[Dict[str, Any]] = Field(default_factory=list)
    timezone: str = "Asia/Riyadh"


class CopMapConfig(BaseModel):
    """Map rendering configuration delivered to the frontend."""

    style: str = "saudi-mod-operational"
    projection: str = "mercator"
    center: List[float] = Field(min_length=2, max_length=2)
    bounds: List[List[float]] = Field(min_length=2, max_length=2)
    zoom: float = 5.2
    min_zoom: float = 3.5
    max_zoom: float = 11.5
    layers: List[str] = Field(default_factory=list)


class CopFeature(BaseModel):
    """Geospatial features shown as overlays on the theater map."""

    feature_id: str
    feature_type: str
    name: str
    geometry_type: str
    coordinates: List[Any] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class CopTrack(BaseModel):
    """Track cards used by tactical map and table widgets."""

    track_id: str
    callsign: str
    domain: str
    affiliation: str
    status: str
    latitude: float
    longitude: float
    altitude_m: float = 0.0
    speed_kts: float = 0.0
    heading_deg: float = 0.0
    confidence: float = 0.0
    last_update: str
    source: str = "cop_service"


class CopAlert(BaseModel):
    """Alert cards surfaced in operational awareness panels."""

    alert_id: str
    category: str
    severity: str
    title: str
    summary: str
    location: Optional[str] = None
    status: str = "active"
    recommended_action: str
    timestamp: str


class CopDecision(BaseModel):
    """Decision-support entries surfaced to command operators."""

    decision_id: str
    title: str
    summary: str
    owner: str
    status: str
    priority: str
    timestamp: str


class CopFeedItem(BaseModel):
    """Live feed item for command and operator chat/activity ribbon."""

    item_id: str
    channel: str
    title: str
    message: str
    language: str = "en"
    tags: List[str] = Field(default_factory=list)
    timestamp: str


class CopPanelState(BaseModel):
    """Compact panel summary for high-density dashboard widgets."""

    panel_id: str
    title: str
    status: str
    summary: str
    metric: Dict[str, Any] = Field(default_factory=dict)
    trend: str = "stable"
    items: List[Dict[str, Any]] = Field(default_factory=list)


class CopState(BaseModel):
    """Normalized COP payload consumed by GUI map and panel components."""

    track: str
    theater: CopTheater
    map_config: CopMapConfig
    geospatial_features: List[CopFeature] = Field(default_factory=list)
    tactical_tracks: List[CopTrack] = Field(default_factory=list)
    alerts: List[CopAlert] = Field(default_factory=list)
    decisions: List[CopDecision] = Field(default_factory=list)
    feed_messages: List[CopFeedItem] = Field(default_factory=list)
    panel_summaries: List[CopPanelState] = Field(default_factory=list)
    backend_health: Dict[str, Any] = Field(default_factory=dict)
    data_source: str = "fallback"
    timestamp: str
