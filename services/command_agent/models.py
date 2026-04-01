"""Data models for multimodal command-agent interactions.

Military context:
These models represent commander session context, parsed intent, and routed
responses for bilingual tactical command and control workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union


class InputModality(str, Enum):
    """Supported commander input modalities for the C2 agent."""

    VOICE = "voice"
    TEXT = "text"
    PDF = "pdf"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    STRUCTURED_COMMAND = "structured_command"


class CommandIntent(str, Enum):
    """Intent taxonomy for command routing in tactical operations."""

    MOVE_UNIT = "move_unit"
    ENGAGE_TARGET = "engage_target"
    AUTHORIZE_KILLCHAIN = "authorize_killchain"
    SET_ROE = "set_roe"
    QUERY_THREATS = "query_threats"
    QUERY_READINESS = "query_readiness"
    QUERY_STATUS = "query_status"
    ANALYZE_RISK = "analyze_risk"
    GENERATE_REPORT = "generate_report"
    GENERATE_BRIEF = "generate_brief"
    UPLOAD_DOCUMENT = "upload_document"
    UPLOAD_DATA = "upload_data"
    UPLOAD_IMAGE = "upload_image"
    SYSTEM_CONTROL = "system_control"
    UNKNOWN = "unknown"


@dataclass
class CommandContext:
    """Commander session context used for intent disambiguation and routing."""

    session_id: str
    commander_id: str
    commander_rank: str
    commander_language: str
    active_mission: Optional[str]
    conversation_history: List[dict]
    current_region: str
    permissions: List[str]


@dataclass
class CommandInput:
    """Normalized command input object after modality preprocessing."""

    input_id: str
    modality: InputModality
    raw_content: Union[str, bytes]
    text_content: Optional[str]
    language: str
    file_path: Optional[str]
    file_type: Optional[str]
    timestamp: datetime


@dataclass
class CommandResponse:
    """Bilingual commander-facing response with route actions and provenance."""

    response_id: str
    input_id: str
    intent: CommandIntent
    text_en: str
    text_ar: str
    structured_data: Optional[dict]
    actions_taken: List[dict] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    confidence: float = 0.0
    follow_up_suggestions: List[str] = field(default_factory=list)
    response_time_ms: float = 0.0
