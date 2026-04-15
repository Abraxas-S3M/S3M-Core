"""Pydantic models for Phase 16 extended interoperability API routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExerciseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    nations: List[Dict[str, Any]] = Field(default_factory=list)
    dis_config: Dict[str, Any] = Field(default_factory=dict)
    c2sim_config: Dict[str, Any] = Field(default_factory=dict)


class ExerciseResponse(BaseModel):
    exercise_id: int
    exercise_name: str
    description: str
    start_time: str
    end_time: Optional[str] = None
    participating_nations: List[Dict[str, Any]]
    status: str
    dis_config: Dict[str, Any]
    c2sim_config: Dict[str, Any]
    entities_count: int
    events_count: int


class ExerciseStartRequest(BaseModel):
    exercise_id: int


class ExerciseInjectRequest(BaseModel):
    scenario: Dict[str, Any] = Field(default_factory=dict)


class PublishEntityRequest(BaseModel):
    entity: Dict[str, Any] = Field(default_factory=dict)


class DISEntityResponse(BaseModel):
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    total: int


class C2SIMOrderRequest(BaseModel):
    order_id: Optional[str] = None
    issuer: str = "S3M-HQ"
    task_type: str = "Move"
    assigned_units: List[str] = Field(default_factory=list)
    waypoints: List[List[float]] = Field(default_factory=list)
    roe: str = "self-defense"
    start_time: Optional[str] = None


class C2SIMReportRequest(BaseModel):
    report_id: Optional[str] = None
    reporter: str = "S3M-Unit"
    report_type: str = "StatusReport"
    content: Dict[str, Any] = Field(default_factory=dict)


class ORBATCreateForceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    affiliation: str = "friendly"
    country_code: int = Field(default=178, ge=1, le=999)


class ORBATAddUnitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    designation: str = Field(..., min_length=1, max_length=256)
    echelon: str
    unit_type: str
    affiliation: str = "friendly"
    country_code: int = Field(default=178, ge=1, le=999)
    parent_unit_id: Optional[str] = None
    strength: int = 0
    equipment: List[Dict[str, Any]] = Field(default_factory=list)
    position: Optional[List[float]] = None
    commander: Optional[str] = None


class ORBATResponse(BaseModel):
    unit_id: str
    name: str
    designation: str
    echelon: str
    unit_type: str
    affiliation: str
    parent_unit_id: Optional[str] = None
    subordinate_ids: List[str] = Field(default_factory=list)
    country_code: int
    nato_symbol: str
    strength: int
    equipment: List[Dict[str, Any]] = Field(default_factory=list)
    position: Optional[List[float]] = None
    commander: Optional[str] = None


class ForceStructureResponse(BaseModel):
    force_id: str
    force_name: str
    affiliation: str
    country_code: int
    units: List[Dict[str, Any]] = Field(default_factory=list)


class MSDLImportRequest(BaseModel):
    xml_str: Optional[str] = None
    filepath: Optional[str] = None


class MSDLExportResponse(BaseModel):
    xml: str
    scenario: Optional[Dict[str, Any]] = None
    force_count: int = 0


class VerificationResponse(BaseModel):
    summary: Dict[str, Any]
    dis: Dict[str, Any]
    c2sim: Dict[str, Any]
    cot: Optional[Dict[str, Any]] = None
    msdl: Dict[str, Any]
    nffi: Dict[str, Any] = Field(default_factory=dict)
    hla: Optional[Dict[str, Any]] = None
    coordinates: Dict[str, Any]
    timestamp: str


class InteropMetricsResponse(BaseModel):
    dis: Dict[str, Any]
    c2sim: Dict[str, Any]
    latency_ms: Dict[str, Any]


class CoalitionCOPResponse(BaseModel):
    timestamp: str
    entities: List[Dict[str, Any]]
    reports: List[Dict[str, Any]]
    exercise_count: int


class ExerciseOverviewResponse(BaseModel):
    exercise: Optional[Dict[str, Any]] = None
    nations: List[Dict[str, Any]] = Field(default_factory=list)
    entities: Dict[str, Any] = Field(default_factory=dict)
    events: Dict[str, Any] = Field(default_factory=dict)
    c2sim_messages: Dict[str, Any] = Field(default_factory=dict)
    dis_pdus: Dict[str, Any] = Field(default_factory=dict)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
