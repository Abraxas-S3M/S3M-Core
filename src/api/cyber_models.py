"""Pydantic models for Phase 13 Cyber Defense Operations API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CaseCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: str = Field(..., min_length=1, max_length=8192)
    severity: str = Field(default="MEDIUM", min_length=1, max_length=32)
    source_events: List[str] = Field(default_factory=list)
    observables: List[Dict[str, Any]] = Field(default_factory=list)
    mitre_tactics: List[str] = Field(default_factory=list)
    mitre_techniques: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class CaseUpdateRequest(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    assigned_analyst: Optional[str] = None
    add_note: Optional[str] = None
    escalate_reason: Optional[str] = None
    tags: Optional[List[str]] = None


class CaseResponse(BaseModel):
    case_id: str
    title: str
    description: str
    severity: str
    status: str
    verdict: Optional[str] = None
    source_events: List[str]
    observables: List[Dict[str, Any]]
    enrichments: List[Dict[str, Any]]
    assigned_analyst: Optional[str] = None
    mitre_tactics: List[str]
    mitre_techniques: List[str]
    playbook_id: Optional[str] = None
    playbook_results: List[Dict[str, Any]]
    llm_analysis: Optional[str] = None
    llm_recommendation: Optional[str] = None
    timeline: List[Dict[str, Any]]
    created_at: str
    updated_at: str
    resolved_at: Optional[str] = None
    tags: List[str]
    classification: str


class TriageEventRequest(BaseModel):
    event_id: Optional[str] = None
    source: str = "MANUAL"
    level: str = "MEDIUM"
    category: str = "CYBER"
    title: str = Field(..., min_length=1, max_length=512)
    description: str = Field(..., min_length=1, max_length=8192)
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class TriageResponse(BaseModel):
    event_id: str
    severity: str
    observables: List[Dict[str, Any]]
    mitre: Optional[Dict[str, Any]] = None
    triage_score: float
    auto_create_case: bool


class PlaybookExecuteRequest(BaseModel):
    playbook_id: str = Field(..., min_length=1, max_length=128)


class PlaybookResponse(BaseModel):
    mode: str
    matched_playbook_id: Optional[str] = None
    result: Dict[str, Any] = Field(default_factory=dict)


class ObservableCreateRequest(BaseModel):
    observable_type: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=4096)
    tlp: str = Field(default="AMBER", min_length=1, max_length=16)
    tags: List[str] = Field(default_factory=list)


class EnrichmentResponse(BaseModel):
    case_id: str
    enrichments: List[Dict[str, Any]]
    total: int


class LogSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)
    backend: str = Field(default="all", min_length=1, max_length=32)


class LogSearchResponse(BaseModel):
    query: str
    backend: str
    results: List[Dict[str, Any]]
    total: int


class SOCOverviewResponse(BaseModel):
    open_cases: int
    cases_by_severity: Dict[str, int]
    cases_by_status: Dict[str, int]
    mean_resolution_hours: float
    alerts_last_hour: int
    playbooks_executed_today: int
    platforms_online: List[str]
    mitre_heatmap: List[Dict[str, Any]]
    top_observables: List[Dict[str, Any]]
    analyst_workload: Dict[str, int]


class AlertQueueResponse(BaseModel):
    alerts: List[Dict[str, Any]]
    total: int


class MITREHeatmapResponse(BaseModel):
    heatmap: List[Dict[str, Any]]
    total: int


class ExerciseCreateRequest(BaseModel):
    scenario_type: str = Field(default="brute_force", min_length=1, max_length=64)


class ExerciseScoreResponse(BaseModel):
    exercise_id: str
    started_at: str
    completed_at: str
    duration_seconds: float
    events_processed: int
    cases_created: int
    playbooks_triggered: int
    analyst_response_time_seconds: float
    pipeline: Dict[str, Any]


class SOCReportResponse(BaseModel):
    report: str


class PlatformStatusResponse(BaseModel):
    thehive: bool
    cortex: bool
    misp: bool
    dfir_iris: bool
