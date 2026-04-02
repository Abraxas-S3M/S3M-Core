"""API endpoints for the S3M Quantum Security Shell."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/security/quantum", tags=["Quantum Security Shell"])

_zkn_manager = None


def _get_zkn():
    global _zkn_manager
    if _zkn_manager is None:
        from src.security.zkn.zkn_manager import ZKNManager
        _zkn_manager = ZKNManager()
    return _zkn_manager


class TunnelRequest(BaseModel):
    source_layer: str
    source_process: str
    dest_layer: str
    dest_process: str


@router.post("/bootstrap")
async def bootstrap_qss() -> Dict[str, Any]:
    """Initialize quantum keys for all S3M layers."""
    return _get_zkn().bootstrap()


@router.get("/status")
async def qss_status() -> Dict[str, Any]:
    return _get_zkn().get_status()


@router.post("/authenticate")
async def authenticate_process(layer_id: str, process_id: str) -> Dict[str, Any]:
    try:
        return _get_zkn().authenticate_process(layer_id, process_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/open")
async def open_tunnel(req: TunnelRequest) -> Dict[str, Any]:
    try:
        return _get_zkn().open_tunnel(
            req.source_layer, req.source_process,
            req.dest_layer, req.dest_process,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tunnel/sessions")
async def list_tunnels() -> List[Dict[str, Any]]:
    return _get_zkn().tunnel.get_active_sessions()


@router.delete("/tunnel/{session_id}")
async def destroy_tunnel(session_id: str) -> Dict[str, Any]:
    success = _get_zkn().tunnel.destroy_tunnel(session_id)
    return {"session_id": session_id, "destroyed": success}


@router.post("/keys/rotate")
async def rotate_keys() -> List[Dict[str, str]]:
    return _get_zkn().rotate_all_keys()


@router.get("/policy/rules")
async def list_policy_rules() -> List[Dict[str, str]]:
    return _get_zkn().policy.list_rules()


@router.get("/perimeter/audit")
async def perimeter_audit() -> Dict[str, Any]:
    from src.security.perimeter.invisibility_enforcer import InvisibilityEnforcer
    enforcer = InvisibilityEnforcer()
    report = enforcer.audit()
    return {
        "timestamp": report.timestamp, "is_invisible": report.is_invisible,
        "public_ips": report.public_ips_found,
        "open_inbound_ports": report.open_inbound_ports,
        "findings": report.findings, "remediation": report.remediation,
    }


@router.get("/perimeter/firewall")
async def get_firewall_rules() -> Dict[str, Any]:
    from src.security.perimeter.invisibility_enforcer import InvisibilityEnforcer
    return InvisibilityEnforcer().enforce_outbound_only()
