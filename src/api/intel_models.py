"""Pydantic models for Phase 19 Intelligence & OSINT API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class IntelReportResponse(BaseModel):
    report_id: str
    title: str
    report_type: str
    classification: str
    date_time_group: str
    originator: str
    summary_en: str
    summary_ar: str
    body_en: str
    body_ar: str
    regions: list[str]
    topics: list[str]
    sources_used: list[str]
    key_findings: list[str]
    risk_assessment: Optional[dict[str, Any]] = None
    recommendations: list[str]
    attachments: list[dict[str, Any]]
    created_at: str
    valid_until: Optional[str] = None
    approved_by: Optional[str] = None


class DailyBriefResponse(BaseModel):
    brief_id: str
    date: str
    classification: str
    executive_summary_en: str
    executive_summary_ar: str
    regions: list[dict[str, Any]]
    top_events: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    recommendations: list[str]
    sources_consulted: int
    items_analyzed: int
    generated_at: str


class WeeklyEstimateResponse(BaseModel):
    estimate_id: str
    week: str
    classification: str
    executive_summary_en: str
    executive_summary_ar: str
    regional_assessments: list[dict[str, Any]]
    trend_analysis: dict[str, Any]
    emerging_threats: list[dict[str, Any]]
    forecast_30_day: str
    generated_at: str


class OSINTItemResponse(BaseModel):
    item_id: str
    source_id: str
    timestamp: str
    title: str
    content: str
    language: str
    url: Optional[str] = None
    regions: list[str]
    topics: list[str]
    entities: list[dict[str, Any]]
    sentiment: str
    relevance_score: float
    summary: Optional[str] = None
    credibility: str


class OSINTItemListResponse(BaseModel):
    items: list[OSINTItemResponse]
    total: int


class IntelSourceResponse(BaseModel):
    source_id: str
    name: str
    source_type: str
    reliability: str
    regions_covered: list[str]
    topics_covered: list[str]
    language: str
    update_frequency: str
    last_ingestion: Optional[str] = None
    items_ingested: int
    data_path: Optional[str] = None
    active: bool


class SourceListResponse(BaseModel):
    sources: list[IntelSourceResponse]
    total: int


class CrisisEventResponse(BaseModel):
    event_id: str
    name: str
    description: str
    severity: str
    region: str
    started_at: str
    last_updated: str
    status: str
    risk_score: float
    related_sources: list[str]
    timeline: list[dict[str, Any]]
    impact_assessment: Optional[str] = None
    active: bool


class CrisisCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=4096)
    severity: str = Field(default="ELEVATED")
    region: str = Field(..., min_length=1, max_length=128)


class CrisisUpdateRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=4096)
    severity_change: Optional[str] = None
    action: Optional[str] = None


class WarningIndicatorResponse(BaseModel):
    indicator_id: str
    name: str
    description: str
    region: str
    topic: str
    threshold: float
    current_value: float
    trend: str
    last_triggered: Optional[str] = None
    active: bool
    triggered: bool


class IndicatorCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=4096)
    region: str = Field(..., min_length=1, max_length=128)
    topic: str = Field(..., min_length=1, max_length=128)
    threshold: float = Field(default=70.0, ge=0.0, le=100.0)


class GenerateReportRequest(BaseModel):
    report_type: str = Field(..., min_length=1, max_length=64)
    region: Optional[str] = None
    topic: Optional[str] = None
    period: Optional[str] = None


class GenerateBriefRequest(BaseModel):
    date: Optional[str] = None
    week: Optional[str] = None


class SearchIntelRequest(BaseModel):
    query: Optional[str] = None
    region: Optional[str] = None
    topic: Optional[str] = None
    min_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    since: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)


class IntelOverviewResponse(BaseModel):
    items_last_24h: int
    items_last_7d: int
    sources_active: int
    sources_by_type: dict[str, int]
    crises_active: int
    crises_by_region: dict[str, int]
    warnings_triggered: list[dict[str, Any]]
    risk_by_region: dict[str, float]
    top_events: list[dict[str, Any]]
    latest_brief: Optional[dict[str, Any]] = None
    collection_health: dict[str, Any]


class RegionIntelResponse(BaseModel):
    region: str
    items: list[dict[str, Any]]
    crises: list[dict[str, Any]]
    risk: dict[str, Any]
    warnings: list[dict[str, Any]]
    recent_reports: list[dict[str, Any]]


class CrisisBoardResponse(BaseModel):
    board: list[dict[str, Any]]


class CollectResponse(BaseModel):
    collection: dict[str, Any]
    monitoring: dict[str, Any]


class SourceHealthResponse(BaseModel):
    sources: list[dict[str, Any]]
    total: int
