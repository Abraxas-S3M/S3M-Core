"""FastAPI routes for out-of-band approver devices (matches src/api style)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.cortex.approvals.models import (
    AdminRegistrationVote,
    ApprovalSubmitBody,
    ApprovalSubmitResponse,
    ChangeRequestBody,
    DevicePayloadResponse,
    DeviceRegisterRequest,
    KillActionBody,
)
from src.cortex.approvals.mtls import optional_session_id, require_mtls_identity
from src.cortex.approvals.service import ApprovalService

approvals_router = APIRouter(prefix="/approvals", tags=["cortex-approvals"])

_service: ApprovalService | None = None


def get_service() -> ApprovalService:
    global _service
    if _service is None:
        _service = ApprovalService()
    return _service


def bind_service(service: ApprovalService) -> None:
    global _service
    _service = service


@approvals_router.post("/devices/register")
async def register_device(
    req: DeviceRegisterRequest,
    identity: str = Depends(require_mtls_identity),
) -> Dict[str, Any]:
    svc = get_service()
    try:
        return svc.start_device_registration(
            device_id=req.device_id,
            public_key_b64=req.public_key_b64,
            approver_label=req.approver_label,
            duress_pin=req.duress_pin,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@approvals_router.post("/devices/register/vote")
async def vote_device_registration(
    req: AdminRegistrationVote,
    identity: str = Depends(require_mtls_identity),
) -> Dict[str, Any]:
    svc = get_service()
    try:
        return svc.admin_approve_registration(registration_id=req.registration_id, admin_id=req.admin_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@approvals_router.post("/changes/{change_id}/request")
async def request_change_approval(
    change_id: str,
    body: ChangeRequestBody,
    identity: str = Depends(require_mtls_identity),
) -> Dict[str, Any]:
    svc = get_service()
    try:
        return svc.request_change_approval(change_id, body.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@approvals_router.get("/changes/{change_id}/payload", response_model=DevicePayloadResponse)
async def get_change_payload(
    change_id: str,
    identity: str = Depends(require_mtls_identity),
) -> DevicePayloadResponse:
    svc = get_service()
    try:
        payload = svc.get_device_payload(change_id, identity)
        return DevicePayloadResponse(**payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@approvals_router.post("/changes/{change_id}/submit", response_model=ApprovalSubmitResponse)
async def submit_change_approval(
    change_id: str,
    body: ApprovalSubmitBody,
    identity: str = Depends(require_mtls_identity),
    session_id: str | None = Depends(optional_session_id),
) -> ApprovalSubmitResponse:
    svc = get_service()
    try:
        result = svc.submit_approval(
            change_id,
            device_id=identity,
            session_id=session_id,
            envelope_id=body.envelope_id,
            decision=body.decision,
            timestamp=body.timestamp,
            nonce=body.nonce,
            signature_b64=body.signature_b64,
            duress_pin=body.duress_pin,
        )
        return ApprovalSubmitResponse(**result)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@approvals_router.post("/kill/engage")
async def engage_kill_switch(
    body: KillActionBody,
    identity: str = Depends(require_mtls_identity),
) -> Dict[str, Any]:
    svc = get_service()
    if body.holder_device_id != identity:
        raise HTTPException(status_code=403, detail="holder identity mismatch")
    try:
        return svc.engage_kill(body.holder_device_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@approvals_router.post("/kill/disengage")
async def disengage_kill_switch(
    body: KillActionBody,
    identity: str = Depends(require_mtls_identity),
) -> Dict[str, Any]:
    svc = get_service()
    if body.holder_device_id != identity:
        raise HTTPException(status_code=403, detail="holder identity mismatch")
    try:
        return svc.disengage_kill(body.holder_device_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
