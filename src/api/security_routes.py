"""FastAPI routes for S3M Phase 10 security and interoperability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.security_models import (
    AirGapVerifyResponse,
    AuditEntryResponse,
    AuditQueryParams,
    AuditVerifyResponse,
    ClassificationResponse,
    ComplianceReportResponse,
    DecryptFileRequest,
    EncryptFileRequest,
    InteropConnectRequest,
    InteropMessageResponse,
    InteropStatusResponse,
    SecurityReportResponse,
    VulnerabilityReportResponse,
)
from src.security import (
    AirGapVerifier,
    ComplianceChecker,
    DataEncryptor,
    InteropManager,
    SecureAuditLog,
    SecurityReportGenerator,
    VulnerabilityScanner,
)
from src.security.crypto import ClassificationBanner
from src.security.input_validator import InputValidator

security_router = APIRouter()

_audit = SecureAuditLog()
_airgap = AirGapVerifier()
_compliance = ComplianceChecker()
_vulnerability = VulnerabilityScanner()
_report_gen = SecurityReportGenerator()
_encryptor = DataEncryptor()
_interop = InteropManager()
_banner = ClassificationBanner(level="UNCLASSIFIED - FOUO")
_latest_security_report: Optional[Dict[str, Any]] = None


def _audit_event(action: str, details: Dict[str, Any], severity: str = "INFO") -> None:
    _audit.log(action=action, details=details, severity=severity, source="security_api")


@security_router.get("/security/status")
async def security_status() -> Dict[str, Any]:
    result = {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "middleware_active": True,
        "auth_mode": "dev",
        "airgap_last_result": _airgap.get_last_result(),
    }
    _audit_event("security_status", {"ok": True})
    return result


@security_router.get("/security/audit", response_model=List[AuditEntryResponse])
async def get_security_audit(
    action: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
) -> List[AuditEntryResponse]:
    params = AuditQueryParams(action=action, severity=severity, source=source, limit=limit)
    rows = _audit.query(
        action=params.action,
        severity=params.severity,
        source=params.source,
        limit=params.limit,
    )
    _audit_event("security_audit_query", params.model_dump())
    return [AuditEntryResponse(**row) for row in rows]


@security_router.get("/security/audit/verify", response_model=AuditVerifyResponse)
async def verify_audit_chain() -> AuditVerifyResponse:
    result = _audit.verify_chain()
    _audit_event("security_audit_verify", {"valid": result.get("valid")})
    return AuditVerifyResponse(
        valid=bool(result.get("valid", False)),
        entries_checked=int(result.get("entries_checked", 0)),
        errors=[str(e) for e in result.get("errors", [])],
    )


@security_router.post("/security/airgap/verify", response_model=AirGapVerifyResponse)
async def verify_airgap_now() -> AirGapVerifyResponse:
    result = _airgap.verify()
    _audit_event("security_airgap_verify", {"air_gapped": result.get("air_gapped")})
    return AirGapVerifyResponse(
        air_gapped=result.get("air_gapped"),
        violations=result.get("violations", []),
        checks_performed=[str(c) for c in result.get("checks_performed", [])],
    )


@security_router.get("/security/airgap/status", response_model=AirGapVerifyResponse)
async def airgap_status() -> AirGapVerifyResponse:
    result = _airgap.get_last_result() or _airgap.verify()
    _audit_event("security_airgap_status", {"has_result": bool(result)})
    return AirGapVerifyResponse(
        air_gapped=result.get("air_gapped"),
        violations=result.get("violations", []),
        checks_performed=[str(c) for c in result.get("checks_performed", [])],
    )


@security_router.post("/security/compliance/check", response_model=ComplianceReportResponse)
async def run_compliance_check() -> ComplianceReportResponse:
    report = _compliance.run_full_check()
    _audit_event("security_compliance_check", {"overall_status": report.get("overall_status")})
    return ComplianceReportResponse(
        overall_status=str(report.get("overall_status", "PARTIAL")),
        checks_passed=int(report.get("checks_passed", 0)),
        checks_failed=int(report.get("checks_failed", 0)),
        checks=report.get("checks", []),
    )


@security_router.get("/security/compliance/report", response_model=ComplianceReportResponse)
async def get_compliance_report() -> ComplianceReportResponse:
    report = _compliance.get_latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No compliance report available")
    _audit_event("security_compliance_report", {"available": True})
    return ComplianceReportResponse(
        overall_status=str(report.get("overall_status", "PARTIAL")),
        checks_passed=int(report.get("checks_passed", 0)),
        checks_failed=int(report.get("checks_failed", 0)),
        checks=report.get("checks", []),
    )


@security_router.post("/security/vulnerability/scan", response_model=VulnerabilityReportResponse)
async def run_vulnerability_scan() -> VulnerabilityReportResponse:
    report = _vulnerability.run_full_scan()
    _audit_event("security_vulnerability_scan", {"findings": report.get("findings_count", 0)})
    return VulnerabilityReportResponse(
        findings_count=int(report.get("findings_count", 0)),
        by_severity=report.get("by_severity", {}),
        findings=report.get("findings", []),
    )


@security_router.get("/security/vulnerability/report", response_model=VulnerabilityReportResponse)
async def get_vulnerability_report() -> VulnerabilityReportResponse:
    report = _vulnerability.get_latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No vulnerability report available")
    _audit_event("security_vulnerability_report", {"available": True})
    return VulnerabilityReportResponse(
        findings_count=int(report.get("findings_count", 0)),
        by_severity=report.get("by_severity", {}),
        findings=report.get("findings", []),
    )


@security_router.post("/security/report/generate", response_model=SecurityReportResponse)
async def generate_security_report() -> SecurityReportResponse:
    global _latest_security_report
    compliance = _compliance.get_latest_report() or _compliance.run_full_check()
    vulnerabilities = _vulnerability.get_latest_report() or _vulnerability.run_full_scan()
    report = _report_gen.generate(compliance, vulnerabilities)
    _latest_security_report = report
    _audit_event("security_report_generate", {"risk": report.get("overall_risk")})
    return SecurityReportResponse(
        overall_risk=str(report.get("overall_risk", "LOW")),
        compliance=report.get("compliance", {}),
        vulnerabilities=report.get("vulnerabilities", {}),
        llm_analysis=report.get("llm_analysis"),
    )


@security_router.get("/security/report", response_model=SecurityReportResponse)
async def get_security_report() -> SecurityReportResponse:
    if _latest_security_report is None:
        raise HTTPException(status_code=404, detail="No combined security report available")
    _audit_event("security_report_get", {"available": True})
    return SecurityReportResponse(
        overall_risk=str(_latest_security_report.get("overall_risk", "LOW")),
        compliance=_latest_security_report.get("compliance", {}),
        vulnerabilities=_latest_security_report.get("vulnerabilities", {}),
        llm_analysis=_latest_security_report.get("llm_analysis"),
    )


@security_router.post("/security/encrypt")
async def encrypt_file(req: EncryptFileRequest) -> Dict[str, Any]:
    valid, reason = InputValidator.validate_file_path(req.filepath)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid filepath: {reason}")
    try:
        out = _encryptor.encrypt_file(req.filepath, key_id=req.key_id)
        _audit_event("security_encrypt", {"filepath": req.filepath, "output": out})
        return {"status": "encrypted", "filepath": req.filepath, "encrypted_filepath": out}
    except Exception as exc:
        _audit_event("security_encrypt_error", {"error": str(exc)}, severity="WARNING")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@security_router.post("/security/decrypt")
async def decrypt_file(req: DecryptFileRequest) -> Dict[str, Any]:
    valid, reason = InputValidator.validate_file_path(req.filepath)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid filepath: {reason}")
    try:
        out = _encryptor.decrypt_file(req.filepath, key_id=req.key_id)
        _audit_event("security_decrypt", {"filepath": req.filepath, "output": out})
        return {"status": "decrypted", "filepath": req.filepath, "decrypted_filepath": out}
    except Exception as exc:
        _audit_event("security_decrypt_error", {"error": str(exc)}, severity="WARNING")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@security_router.get("/security/classification", response_model=ClassificationResponse)
async def get_classification() -> ClassificationResponse:
    level = _banner.get_level()
    html = _banner.get_banner_html()
    _audit_event("security_classification_get", {"level": level})
    return ClassificationResponse(level=level, banner_html=html)


@security_router.get("/security/interop/status", response_model=InteropStatusResponse)
async def get_interop_status() -> InteropStatusResponse:
    status = _interop.get_protocol_status()
    _audit_event("security_interop_status", {"protocols": list(status.keys())})
    return InteropStatusResponse(protocols=status)


@security_router.post("/security/interop/{protocol}/connect")
async def connect_interop(protocol: str, req: InteropConnectRequest) -> Dict[str, Any]:
    config = dict(req.config)
    if req.host:
        if protocol.lower() == "c2sim":
            scheme = "http://"
            host_part = req.host
            if host_part.startswith("http://") or host_part.startswith("https://"):
                scheme = ""
            if req.port is not None:
                config["server_url"] = f"{scheme}{host_part}:{req.port}"
            else:
                config["server_url"] = f"{scheme}{host_part}"
        else:
            if req.port is not None:
                config["port"] = req.port
            config["host"] = req.host
    ok = _interop.enable_protocol(protocol, config=config)
    _audit_event("security_interop_connect", {"protocol": protocol, "connected": ok})
    if not ok and protocol.lower() not in {"c2sim"}:
        raise HTTPException(status_code=400, detail=f"Failed to connect protocol: {protocol}")
    return {"protocol": protocol, "connected": ok, "status": _interop.get_protocol_status().get(protocol.lower(), {})}


@security_router.post("/security/interop/{protocol}/disconnect")
async def disconnect_interop(protocol: str) -> Dict[str, Any]:
    _interop.disable_protocol(protocol)
    _audit_event("security_interop_disconnect", {"protocol": protocol})
    return {"protocol": protocol, "connected": False}


@security_router.get("/security/interop/messages", response_model=List[InteropMessageResponse])
async def get_interop_messages(
    protocol: Optional[str] = Query(default=None),
    direction: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=5000),
) -> List[InteropMessageResponse]:
    rows = _interop.get_message_history(protocol=protocol, direction=direction, limit=limit)
    _audit_event(
        "security_interop_messages_query",
        {"protocol": protocol, "direction": direction, "limit": limit, "rows": len(rows)},
    )
    return [
        InteropMessageResponse(
            protocol=str(row.get("protocol", "")),
            message_type=str(row.get("message_type", "")),
            data=row.get("data", {}),
            timestamp=str(row.get("timestamp", "")),
        )
        for row in rows
    ]
