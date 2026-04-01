"""Pydantic models for S3M Phase 14 secure communications API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    sender_callsign: str = Field(..., min_length=1, max_length=128)
    recipients: List[str] = Field(..., min_length=1)
    body: str = Field(..., min_length=1, max_length=65536)
    message_type: str = Field(..., min_length=1, max_length=64)
    priority: str = Field(..., min_length=1, max_length=32)
    language: str = Field(default="auto", min_length=2, max_length=16)
    channel_id: Optional[str] = Field(default=None, max_length=256)
    encrypt: bool = True


class SendOrderRequest(BaseModel):
    sender: str = Field(..., min_length=1, max_length=128)
    recipients: List[str] = Field(..., min_length=1)
    order_text: str = Field(..., min_length=1, max_length=65536)
    priority: str = Field(default="PRIORITY", min_length=1, max_length=32)


class SendSitrepRequest(BaseModel):
    sender: str = Field(..., min_length=1, max_length=128)
    sitrep_text: str = Field(..., min_length=1, max_length=65536)


class BroadcastAlertRequest(BaseModel):
    sender: str = Field(..., min_length=1, max_length=128)
    alert_text: str = Field(..., min_length=1, max_length=65536)


class MessageResponse(BaseModel):
    message_id: str
    status: str
    backend: Optional[str] = None
    routed_to: List[str] = Field(default_factory=list)
    urgency: float = 0.0
    nlp_summary: Optional[str] = None
    intel: Dict[str, Any] = Field(default_factory=dict)


class MessageListResponse(BaseModel):
    messages: List[Dict[str, Any]]
    total: int


class CreateChannelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    channel_type: str = Field(..., min_length=1, max_length=64)
    members: List[str] = Field(..., min_length=1)
    backend: Optional[str] = Field(default=None, max_length=64)


class ChannelResponse(BaseModel):
    channel_id: str
    name: str
    channel_type: str
    members: List[str]
    relay_backend: str
    encryption_required: bool
    priority_default: str
    active: bool
    created_at: str


class RegisterNodeRequest(BaseModel):
    callsign: str = Field(..., min_length=1, max_length=128)
    node_type: str = Field(..., min_length=1, max_length=64)
    relay_backends: List[str] = Field(..., min_length=1)
    position: Optional[Tuple[float, float, float]] = None


class NodeResponse(BaseModel):
    node_id: str
    callsign: str
    node_type: str
    relay_backends: List[str]
    position: Optional[Tuple[float, float, float]] = None
    last_heartbeat: str
    status: str
    signal_strength: float
    battery_pct: Optional[float] = None


class BackendStatusResponse(BaseModel):
    backend_status: Dict[str, str]


class NetworkStatusResponse(BaseModel):
    relay: Dict[str, Any]
    nodes: Dict[str, Any]
    message_stats: Dict[str, Any]
    nlp: Dict[str, Any]


class CommsBriefResponse(BaseModel):
    brief: str


class ChannelTrafficResponse(BaseModel):
    channel_id: str
    window_minutes: int
    message_count: int
    messages: List[Dict[str, Any]]
    summary: Dict[str, Any]


class NLPSummaryResponse(BaseModel):
    message_id: str
    original_language: str
    summary_ar: Optional[str] = None
    summary_en: Optional[str] = None
    entities: List[Dict[str, Any]]
    intent: str
    urgency_score: float
    sentiment: str
    model_used: str
    processing_time_ms: float


class NLPModelInfoResponse(BaseModel):
    model_info: Dict[str, Any]
