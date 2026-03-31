"""Pydantic models for Phase 11 domain application API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class MissionBriefRequest(BaseModel):
    brief: str = Field(..., min_length=1, max_length=4096)
    language: str = Field(default="en", pattern="^(en|ar)$")
    options: Optional[dict] = None


class OPORDResponse(BaseModel):
    opord: Dict[str, Any]


class COAComparisonResponse(BaseModel):
    mission_brief: str
    coas: List[Dict[str, Any]]
    comparison: Dict[str, Any]
    recommendation: str
    llm_analysis: str


class SupplyDataRequest(BaseModel):
    records: List[dict] = Field(default_factory=list)


class DisruptionPredictionResponse(BaseModel):
    total_shipments: int
    anomalies_detected: int
    disruptions: List[Dict[str, Any]]
    overall_risk: str


class RouteOptimizeRequest(BaseModel):
    origin: Tuple[float, float, float]
    destination: Tuple[float, float, float]
    threats: Optional[List[dict]] = None
    platform_type: str = "ground_wheeled"


class RouteResponse(BaseModel):
    route_id: str
    primary_route: Dict[str, Any]
    alternative_route: Optional[Dict[str, Any]] = None
    recommendation: str
    threat_summary: str


class InventoryItemRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    category: str = Field(..., min_length=1, max_length=128)
    quantity: int = Field(..., ge=0)
    location: str = Field(..., min_length=1, max_length=256)
    reorder_threshold: int = Field(..., ge=0)
    unit: str = Field(default="units", min_length=1, max_length=64)


class InventoryResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int


class RestockResponse(BaseModel):
    restock_items: List[Dict[str, Any]]
    total: int


class CorrelateRequest(BaseModel):
    events: Optional[List[dict]] = None


class CorrelationResponse(BaseModel):
    correlations: List[Dict[str, Any]]
    escalations: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None


class OSINTAnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)
    files: Optional[List[str]] = None


class IntelResponse(BaseModel):
    query: str
    analysis: str
    confidence: float
    sources_used: List[str]
    timestamp: str


class EscalationRuleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    condition: str = Field(..., min_length=1, max_length=512)
    action: str = Field(..., min_length=1, max_length=128)
    auto_response: bool = False
    priority: int = Field(default=3, ge=1, le=10)


class EscalationResponse(BaseModel):
    escalations: List[Dict[str, Any]]
    total: int


class GeopoliticalEventRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=4096)
    region: str = Field(..., min_length=1, max_length=256)


class RiskAnalysisResponse(BaseModel):
    result: Dict[str, Any]


class ForecastResponse(BaseModel):
    forecast: Dict[str, Any]


class DroneMissionRequest(BaseModel):
    mission_type: str = Field(..., min_length=1, max_length=128)
    waypoints: List[Tuple[float, float, float]] = Field(..., min_length=1)
    num_agents: int = Field(default=1, ge=1, le=32)
    roe: str = Field(default="weapons_tight", min_length=1, max_length=128)
    platform_type: str = Field(default="quadrotor", min_length=1, max_length=128)
    description: str = Field(default="", max_length=2048)


class DroneMissionResponse(BaseModel):
    mission: Optional[Dict[str, Any]] = None
    autopilot_connected: Optional[bool] = None
    timestamp: Optional[str] = None
    mission_id: Optional[str] = None
    mission_type: Optional[str] = None
    status: Optional[str] = None
    agents_assigned: Optional[Dict[str, str]] = None
    waypoints: Optional[List[Tuple[float, float, float]]] = None


class NLMissionRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    language: str = Field(default="en", pattern="^(en|ar)$")


class FleetStatusResponse(BaseModel):
    missions: List[Dict[str, Any]]
    telemetry: Dict[str, Any]
    planner_stats: Dict[str, Any]
    timestamp: str


class BenchmarkRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=64)
    model_id: Optional[str] = None
    task: str = Field(default="detection", pattern="^(detection|anomaly)$")


class BenchmarkResponse(BaseModel):
    benchmark_id: str
    dataset_id: str
    model_id: str
    task: str
    metrics: Dict[str, Any]
    samples_evaluated: int
    duration_ms: float
    timestamp: str


class DatasetListResponse(BaseModel):
    datasets: List[Dict[str, Any]]
    total: int


class DatasetDetailResponse(BaseModel):
    dataset: Optional[Dict[str, Any]]
