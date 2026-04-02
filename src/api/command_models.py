"""Pydantic models for Mission Command Engine API routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.command.mission_command_engine import EventType


class MCEventRequest(BaseModel):
    event_type: EventType
    source_layer: str = Field(..., min_length=1, max_length=128)
    payload: Dict[str, Any]
    event_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    timestamp: Optional[str] = Field(default=None, min_length=1, max_length=64)
    classification: str = Field(default="UNCLASSIFIED-FOUO", min_length=1, max_length=128)


class ApprovalResolveRequest(BaseModel):
    ticket_id: str = Field(..., min_length=1, max_length=128)
    granted: bool
    resolver: str = Field(..., min_length=1, max_length=128)
