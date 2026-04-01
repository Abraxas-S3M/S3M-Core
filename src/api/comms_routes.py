"""FastAPI routes for S3M Phase 14 secure communications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.comms import CommsManager
from services.comms.models import ChannelType, MessagePriority, MessageType, NodeType, RelayBackend
from src.api.comms_models import (
    BackendStatusResponse,
    BroadcastAlertRequest,
    ChannelResponse,
    ChannelTrafficResponse,
    CommsBriefResponse,
    CreateChannelRequest,
    MessageListResponse,
    MessageResponse,
    NLPModelInfoResponse,
    NLPSummaryResponse,
    NetworkStatusResponse,
    NodeResponse,
    RegisterNodeRequest,
    SendMessageRequest,
    SendOrderRequest,
    SendSitrepRequest,
)

comms_router = APIRouter()

_manager = CommsManager()
_audit_log: List[Dict[str, Any]] = []


def _audit(action: str, details: Dict[str, Any]) -> None:
    # Tactical security requirement: never include plaintext body in logs.
    _audit_log.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details,
        }
    )
    if len(_audit_log) > 2000:
        del _audit_log[:-2000]


def _as_message_response(payload: Dict[str, Any]) -> MessageResponse:
    return MessageResponse(**payload)


def _parse_message_type(value: str) -> MessageType:
    return MessageType(str(value).upper())


def _parse_priority(value: str) -> MessagePriority:
    return MessagePriority[str(value).upper()]


def _parse_channel_type(value: str) -> ChannelType:
    return ChannelType(str(value).upper())


def _parse_backend(value: str) -> RelayBackend:
    return RelayBackend(str(value).lower())


def _parse_node_type(value: str) -> NodeType:
    return NodeType(str(value).lower())


@comms_router.post("/comms/send", response_model=MessageResponse)
async def send_message(req: SendMessageRequest) -> MessageResponse:
    try:
        result = _manager.send_message(
            sender_callsign=req.sender_callsign,
            recipients=req.recipients,
            body=req.body,
            message_type=_parse_message_type(req.message_type),
            priority=_parse_priority(req.priority),
            language=req.language,
            channel_id=req.channel_id,
            encrypt=req.encrypt,
        )
    except Exception as exc:
        _audit("comms_send_error", {"sender_callsign": req.sender_callsign, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(
        "comms_send",
        {
            "sender_callsign": req.sender_callsign,
            "recipients_count": len(req.recipients),
            "message_type": req.message_type,
            "priority": req.priority,
        },
    )
    return _as_message_response(result)


@comms_router.post("/comms/order", response_model=MessageResponse)
async def send_order(req: SendOrderRequest) -> MessageResponse:
    try:
        result = _manager.send_order(req.sender, req.recipients, req.order_text, _parse_priority(req.priority))
    except Exception as exc:
        _audit("comms_order_error", {"sender": req.sender, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("comms_order", {"sender": req.sender, "recipients_count": len(req.recipients)})
    return _as_message_response(result)


@comms_router.post("/comms/sitrep", response_model=MessageResponse)
async def send_sitrep(req: SendSitrepRequest) -> MessageResponse:
    try:
        result = _manager.send_sitrep(req.sender, req.sitrep_text)
    except Exception as exc:
        _audit("comms_sitrep_error", {"sender": req.sender, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("comms_sitrep", {"sender": req.sender})
    return _as_message_response(result)


@comms_router.post("/comms/alert", response_model=MessageResponse)
async def broadcast_alert(req: BroadcastAlertRequest) -> MessageResponse:
    try:
        result = _manager.broadcast_alert(req.sender, req.alert_text)
    except Exception as exc:
        _audit("comms_alert_error", {"sender": req.sender, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("comms_alert", {"sender": req.sender})
    return _as_message_response(result)


@comms_router.get("/comms/messages", response_model=MessageListResponse)
async def get_messages(
    channel_id: Optional[str] = Query(default=None),
    backend: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> MessageListResponse:
    since_dt: Optional[datetime] = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="since must be ISO datetime") from exc
    try:
        messages = _manager.receive_messages(channel_id=channel_id, backend=backend, since=since_dt)
    except Exception as exc:
        _audit("comms_channels_traffic_error", {"channel_id": channel_id, "error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = [m.to_log_safe() for m in messages][-limit:]
    _audit("comms_messages", {"channel_id": channel_id, "backend": backend, "count": len(payload)})
    return MessageListResponse(messages=payload, total=len(payload))


@comms_router.post("/comms/channels", response_model=ChannelResponse)
async def create_channel(req: CreateChannelRequest) -> ChannelResponse:
    try:
        channel = _manager.create_channel(
            name=req.name,
            channel_type=_parse_channel_type(req.channel_type),
            members=req.members,
            backend=_parse_backend(req.backend) if req.backend else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("comms_create_channel", {"name": req.name, "channel_type": req.channel_type})
    return ChannelResponse(**channel.to_dict())


@comms_router.get("/comms/channels")
async def list_channels(
    backend: Optional[str] = Query(default=None),
    channel_type: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    try:
        channels = _manager.get_channels()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if backend:
        channels = [c for c in channels if c.relay_backend == backend]
    if channel_type:
        channels = [c for c in channels if c.channel_type.value == channel_type]
    payload = [c.to_dict() for c in channels]
    _audit("comms_list_channels", {"backend": backend, "channel_type": channel_type, "count": len(payload)})
    return {"channels": payload, "total": len(payload)}


@comms_router.get("/comms/channels/{channel_id}/traffic", response_model=ChannelTrafficResponse)
async def channel_traffic(channel_id: str, minutes: int = Query(default=60, ge=1, le=1440)) -> ChannelTrafficResponse:
    payload = _manager.c2_router.get_channel_traffic(channel_id=channel_id, minutes=minutes)
    return ChannelTrafficResponse(**payload)


@comms_router.post("/comms/nodes", response_model=NodeResponse)
async def register_node(req: RegisterNodeRequest) -> NodeResponse:
    try:
        node = _manager.register_node(
            callsign=req.callsign,
            node_type=_parse_node_type(req.node_type),
            backends=[_parse_backend(v) for v in req.relay_backends],
            position=tuple(req.position) if req.position else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit("comms_register_node", {"callsign": req.callsign, "node_type": req.node_type})
    return NodeResponse(**node.to_dict())


@comms_router.get("/comms/nodes")
async def list_nodes(
    node_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    try:
        parsed_node_type = _parse_node_type(node_type) if node_type else None
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid node_type: {node_type}") from exc
    nodes = _manager.node_manager.get_nodes(node_type=parsed_node_type, status=status)
    payload = [n.to_dict() for n in nodes]
    return {"nodes": payload, "total": len(payload)}


@comms_router.post("/comms/nodes/{node_id}/heartbeat")
async def node_heartbeat(node_id: str) -> Dict[str, Any]:
    _manager.node_manager.heartbeat(node_id)
    return {"status": "ok", "node_id": node_id}


@comms_router.get("/comms/nodes/topology")
async def node_topology() -> Dict[str, Any]:
    return _manager.node_manager.get_network_topology()


@comms_router.get("/comms/status", response_model=NetworkStatusResponse)
async def comms_status() -> NetworkStatusResponse:
    return NetworkStatusResponse(**_manager.get_network_status())


@comms_router.get("/comms/backends", response_model=BackendStatusResponse)
async def comms_backends() -> BackendStatusResponse:
    status = _manager.relay_manager.get_backend_status()
    return BackendStatusResponse(backend_status={k: v.value for k, v in status.items()})


@comms_router.get("/comms/brief", response_model=CommsBriefResponse)
async def comms_brief(minutes: int = Query(default=60, ge=1, le=1440)) -> CommsBriefResponse:
    brief = _manager.get_comms_brief(minutes=minutes)
    return CommsBriefResponse(brief=brief)


@comms_router.get("/comms/stats")
async def comms_stats() -> Dict[str, Any]:
    return _manager.relay_manager.get_message_stats()


class _SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    language: str = Field(default="auto")


@comms_router.post("/comms/nlp/summarize", response_model=NLPSummaryResponse)
async def nlp_summarize(req: _SummarizeRequest) -> NLPSummaryResponse:
    summary = _manager.nlp_engine.summarize(req.text, language=req.language)
    return NLPSummaryResponse(**summary.to_dict())


@comms_router.get("/comms/nlp/model", response_model=NLPModelInfoResponse)
async def nlp_model_info() -> NLPModelInfoResponse:
    return NLPModelInfoResponse(model_info=_manager.nlp_engine.get_model_info())
