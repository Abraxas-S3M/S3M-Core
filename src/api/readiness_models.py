"""Pydantic schemas for Phase 20 Personnel & Readiness API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RegisterMemberRequest(BaseModel):
    name_en: str = Field(..., min_length=1, max_length=128)
    name_ar: str = Field(..., min_length=1, max_length=128)
    rank: str = Field(..., min_length=1, max_length=64)
    branch: str = Field(..., min_length=1, max_length=64)
    mos: str = Field(..., min_length=1, max_length=32)
    mos_desc_en: str = Field(..., min_length=1, max_length=256)
    mos_desc_ar: str = Field(..., min_length=1, max_length=256)
    unit_id: str = Field(..., min_length=1, max_length=128)
    unit_name_en: str = Field(..., min_length=1, max_length=256)
    unit_name_ar: str = Field(..., min_length=1, max_length=256)
    service_number: Optional[str] = None
    clearance: str = Field(default="CONFIDENTIAL")
    medical: str = Field(default="FIT_FOR_DUTY")
    languages: List[str] = Field(default_factory=lambda: ["ar", "en"])
    specializations: List[str] = Field(default_factory=list)


class MemberResponse(BaseModel):
    member_id: str
    service_number: str
    name_en: str
    name_ar: str
    rank: str
    branch: str
    mos: str
    status: str
    clearance: str
    medical: str
    unit_id: str
    unit_name_en: str
    unit_name_ar: str
    years_of_service: float
    training_score: Optional[float] = None
    eligible_for_deployment: bool
    languages: List[str]
    specializations: List[str]
    contact_redacted: bool = True


class PromoteRequest(BaseModel):
    member_id: str
    new_rank: str


class UpdateStatusRequest(BaseModel):
    member_id: str
    status: str


class UpdateMedicalRequest(BaseModel):
    member_id: str
    medical: str


class IssueCertRequest(BaseModel):
    member_id: str
    type: str
    name_en: str
    name_ar: str
    authority: str
    score: Optional[float] = None
    expiry_days: int = Field(default=365, ge=0, le=3650)
    course_id: Optional[str] = None
    exercise_id: Optional[str] = None


class CertResponse(BaseModel):
    cert_id: str
    member_id: str
    certification_type: str
    name_en: str
    name_ar: str
    status: str
    issued_date: str
    expiry_date: Optional[str] = None
    issuing_authority: str
    score: Optional[float] = None
    linked_course_id: Optional[str] = None
    linked_exercise_id: Optional[str] = None


class CreateUnitRequest(BaseModel):
    name_en: str
    name_ar: str
    authorized_strength: int = Field(..., ge=1, le=200000)
    orbat_unit_id: Optional[str] = None


class UnitManningResponse(BaseModel):
    unit_id: str
    unit_name_en: str
    unit_name_ar: str
    orbat_unit_id: Optional[str] = None
    authorized_strength: int
    assigned_strength: int
    slots: List[Dict[str, Any]]
    commander_id: Optional[str] = None


class AddSlotRequest(BaseModel):
    unit_id: str
    position_title_en: str
    position_title_ar: str
    required_rank: str
    required_mos: str
    required_clearance: str = Field(default="CONFIDENTIAL")
    required_certs: List[str] = Field(default_factory=list)


class FillSlotRequest(BaseModel):
    unit_id: str
    slot_id: str
    member_id: str


class ManningSlotResponse(BaseModel):
    slot_id: str
    unit_id: str
    position_title_en: str
    position_title_ar: str
    required_rank: str
    required_mos: str
    required_clearance: str
    required_certifications: List[str]
    filled_by: Optional[str] = None
    status: str


class EligibilityResponse(BaseModel):
    member_id: str
    eligible: bool
    checks: List[Dict[str, Any]]
    overall_readiness: str
    disqualifiers: List[str]
    recommendations: List[str]


class ReadinessScoreResponse(BaseModel):
    unit_id: str
    timestamp: str
    personnel_readiness: float
    training_readiness: float
    equipment_readiness: float
    overall_readiness: float
    readiness_level: str
    manning_fill_rate: float
    certification_rate: float
    deployment_eligible_rate: float
    critical_shortages: List[str]
    expired_certifications: int
    llm_assessment: Optional[str] = None


class ForceReadinessResponse(BaseModel):
    overall_readiness: float
    readiness_level: str
    units: List[Dict[str, Any]]
    force_green_pct: float
    force_amber_pct: float
    force_red_pct: float


class CoalitionRegisterRequest(BaseModel):
    partner_code: int
    personnel: List[Dict[str, Any]]


class CoalitionRosterResponse(BaseModel):
    roster: List[Dict[str, Any]]


class ReadinessOverviewResponse(BaseModel):
    total_personnel: int
    deployable: int
    deployable_pct: float
    by_branch: Dict[str, int]
    by_rank_group: Dict[str, int]
    by_status: Dict[str, int]
    units: List[Dict[str, Any]]
    expiring_certs_30d: int
    expired_certs: int
    critical_vacancies: int
    overall_readiness: float
    readiness_level: str
    coalition_partners: int


class UnitDetailResponse(BaseModel):
    unit: Dict[str, Any]
    roster: List[Dict[str, Any]]
    manning_table: List[Dict[str, Any]]
    fill_rate: float
    vacancies: int
    critical_vacancies: List[Dict[str, Any]]
    readiness_score: Dict[str, Any]
    cert_status: List[Dict[str, Any]]


class MemberProfileResponse(BaseModel):
    member: Dict[str, Any]
    certifications: List[Dict[str, Any]]
    deployments: List[Dict[str, Any]]
    eligibility: Dict[str, Any]
    training_score: Optional[float] = None


class ManningBoardResponse(BaseModel):
    units: List[Dict[str, Any]]


class ReadinessReportResponse(BaseModel):
    report: str


class MemberQueryParams(BaseModel):
    unit_id: Optional[str] = None
    rank: Optional[str] = None
    branch: Optional[str] = None
    status: Optional[str] = None
    mos: Optional[str] = None
    deployable_only: bool = False
    limit: int = Field(default=200, ge=1, le=100000)
