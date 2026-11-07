"""API endpoints for the S3M Quantum Security Shell.

Route paths under ``/security/quantum`` are stable for one release; handlers now
use ``src.security.internal_channel`` (replacing legacy ZKN module names).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/security/quantum", tags=["Quantum Security Shell"])

_channel_manager = None


def _get_channel_manager():
    global _channel_manager
    if _channel_manager is None:
        from src.security.internal_channel.channel_manager import ChannelManager

        _channel_manager = ChannelManager()
    return _channel_manager


class TunnelRequest(BaseModel):
    source_layer: str
    source_process: str
    dest_layer: str
    dest_process: str


@router.post("/bootstrap")
async def bootstrap_qss() -> Dict[str, Any]:
    """Initialize quantum keys for all S3M layers."""
    return _get_channel_manager().bootstrap()


@router.get("/status")
async def qss_status() -> Dict[str, Any]:
    return _get_channel_manager().get_status()


@router.post("/authenticate")
async def authenticate_process(layer_id: str, process_id: str) -> Dict[str, Any]:
    try:
        return _get_channel_manager().authenticate_process(layer_id, process_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tunnel/open")
async def open_tunnel(req: TunnelRequest) -> Dict[str, Any]:
    try:
        return _get_channel_manager().open_tunnel(
            req.source_layer, req.source_process,
            req.dest_layer, req.dest_process,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tunnel/sessions")
async def list_tunnels() -> List[Dict[str, Any]]:
    return _get_channel_manager().tunnel.get_active_sessions()


@router.delete("/tunnel/{session_id}")
async def destroy_tunnel(session_id: str) -> Dict[str, Any]:
    success = _get_channel_manager().tunnel.destroy_tunnel(session_id)
    return {"session_id": session_id, "destroyed": success}


@router.post("/keys/rotate")
async def rotate_keys() -> List[Dict[str, str]]:
    return _get_channel_manager().rotate_all_keys()


@router.get("/policy/rules")
async def list_policy_rules() -> List[Dict[str, str]]:
    return _get_channel_manager().policy.list_rules()


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
