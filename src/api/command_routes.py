"""FastAPI routes for Mission Command Engine command and approval control."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from src.api.command_models import ApprovalResolveRequest, MCEventRequest
from src.command.mission_command_engine import MCEvent, MissionCommandEngine

command_router = APIRouter()
_mce = MissionCommandEngine()


@command_router.get("/command/cop")
async def get_cop() -> Dict[str, Any]:
    return _mce.get_cop_snapshot()


@command_router.post("/command/ingest")
async def ingest_event(req: MCEventRequest) -> Dict[str, Any]:
    payload = req.model_dump(exclude_none=True)
    event = MCEvent(**payload)
    await _mce.ingest(event)
    return {"status": "ingested", "event_id": event.event_id}


@command_router.post("/command/approve")
async def approve_action(req: ApprovalResolveRequest) -> Dict[str, Any]:
    ticket = await _mce.resolve_approval(
        ticket_id=req.ticket_id,
        granted=req.granted,
        resolver=req.resolver,
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found or invalid request")
    return {"status": "resolved", "ticket": asdict(ticket)}


@command_router.get("/command/pending")
async def get_pending_approvals() -> List[Dict[str, Any]]:
    return [asdict(ticket) for ticket in _mce.gate.get_pending()]
