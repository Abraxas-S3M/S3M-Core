"""FastAPI routes for FMN coalition security profile services."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.interop.fmn_security import FMNSecurityManager
from services.interop.fmn_security.security_labels import NATOSecurityLabel

fmn_security_router = APIRouter()
_manager = FMNSecurityManager()


class LabelMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=200000)
    classification: str = Field(default="NATO UNCLASSIFIED", min_length=1, max_length=64)
    releasable_to: list[str] = Field(default_factory=lambda: ["SAU"])


class ValidateIncomingRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=200000)


class EnforcePolicyRequest(BaseModel):
    operation: str = Field(..., min_length=1, max_length=128)
    user: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class RegisterCoalitionUserRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=256)
    nation: str = Field(..., min_length=3, max_length=3)
    clearance: str = Field(..., min_length=1, max_length=64)
    roles: list[str] = Field(default_factory=list)


class CertificateAuthRequest(BaseModel):
    cert_pem: str = Field(..., min_length=1, max_length=200000)


class ValidateTokenRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=200000)


class LabelXmlRequest(BaseModel):
    classification: str = Field(..., min_length=1, max_length=64)
    policy_identifier: str = Field(default="NATO", min_length=1, max_length=128)
    releasable_to: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class LabelXmlParseRequest(BaseModel):
    xml_str: str = Field(..., min_length=1, max_length=200000)


@fmn_security_router.get("/security/fmn/status")
async def fmn_status() -> dict[str, Any]:
    return {
        "status": "operational",
        "enforce_labels": bool(_manager.config.get("enforce_labels", False)),
        "default_classification": _manager.default_label.classification,
        "default_releasable_to": list(_manager.default_label.releasable_to),
    }


@fmn_security_router.post("/security/fmn/label")
async def label_message(req: LabelMessageRequest) -> dict[str, Any]:
    try:
        labeled = _manager.label_message(
            message=req.message,
            classification=req.classification,
            releasable_to=req.releasable_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"labeled_message": labeled}


@fmn_security_router.post("/security/fmn/validate")
async def validate_incoming(req: ValidateIncomingRequest) -> dict[str, Any]:
    valid, reason = _manager.validate_incoming(req.message)
    return {"valid": valid, "reason": reason}


@fmn_security_router.post("/security/fmn/enforce")
async def enforce_policy(req: EnforcePolicyRequest) -> dict[str, Any]:
    allowed = _manager.enforce_policy(req.operation, req.user, req.data)
    return {"allowed": allowed}


@fmn_security_router.post("/security/fmn/users/register")
async def register_user(req: RegisterCoalitionUserRequest) -> dict[str, Any]:
    try:
        user = _manager.identity_provider.register_coalition_user(
            user_id=req.user_id,
            nation=req.nation,
            clearance=req.clearance,
            roles=req.roles,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user}


@fmn_security_router.get("/security/fmn/users/roster")
async def get_roster() -> dict[str, Any]:
    roster = _manager.identity_provider.get_coalition_roster()
    return {"count": len(roster), "users": roster}


@fmn_security_router.post("/security/fmn/auth/certificate")
async def authenticate_certificate(req: CertificateAuthRequest) -> dict[str, Any]:
    try:
        identity = _manager.identity_provider.authenticate_certificate(req.cert_pem)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"identity": identity}


@fmn_security_router.post("/security/fmn/auth/token")
async def validate_token(req: ValidateTokenRequest) -> dict[str, Any]:
    try:
        payload = _manager.identity_provider.validate_token(req.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"token": payload}


@fmn_security_router.post("/security/fmn/labels/xml")
async def label_to_xml(req: LabelXmlRequest) -> dict[str, Any]:
    try:
        label = NATOSecurityLabel(
            classification=req.classification,
            policy_identifier=req.policy_identifier,
            releasable_to=req.releasable_to,
            caveats=req.caveats,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"xml": label.to_xml(), "label": label.build_label()}


@fmn_security_router.post("/security/fmn/labels/xml/parse")
async def label_from_xml(req: LabelXmlParseRequest) -> dict[str, Any]:
    try:
        label = NATOSecurityLabel.from_xml(req.xml_str)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"label": label.build_label()}
