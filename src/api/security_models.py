"""Pydantic models for Phase 10 security and interoperability endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AirGapVerifyResponse(BaseModel):
    air_gapped: Optional[bool] = None
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    checks_performed: List[str] = Field(default_factory=list)


class ComplianceReportResponse(BaseModel):
    overall_status: str
    checks_passed: int
    checks_failed: int
    checks: List[Dict[str, Any]]


class VulnerabilityReportResponse(BaseModel):
    findings_count: int
    by_severity: Dict[str, int]
    findings: List[Dict[str, Any]]


class SecurityReportResponse(BaseModel):
    overall_risk: str
    compliance: Dict[str, Any]
    vulnerabilities: Dict[str, Any]
    llm_analysis: Optional[str] = None


class AuditQueryParams(BaseModel):
    action: Optional[str] = None
    severity: Optional[str] = None
    source: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=5000)


class AuditEntryResponse(BaseModel):
    entry_id: str
    timestamp: str
    action: str
    severity: str
    source: str
    details: Dict[str, Any]
    previous_hash: str
    entry_hash: str


class AuditVerifyResponse(BaseModel):
    valid: bool
    entries_checked: int
    errors: List[str]


class EncryptFileRequest(BaseModel):
    filepath: str = Field(..., min_length=1, max_length=4096)
    key_id: str = Field(default="default", min_length=1, max_length=128)


class DecryptFileRequest(BaseModel):
    filepath: str = Field(..., min_length=1, max_length=4096)
    key_id: str = Field(default="default", min_length=1, max_length=128)


class InteropStatusResponse(BaseModel):
    protocols: Dict[str, Dict[str, Any]]


class InteropConnectRequest(BaseModel):
    protocol: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    config: Dict[str, Any] = Field(default_factory=dict)


class InteropMessageResponse(BaseModel):
    protocol: str
    message_type: str
    data: Dict[str, Any]
    timestamp: str


class ClassificationResponse(BaseModel):
    level: str
    banner_html: str
