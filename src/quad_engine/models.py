"""Pydantic schemas for the S3M-Core Quad-Engine Orchestration Demo Layer.

Tactical context:
    These schemas define the contract between S3M-Core and S3M-GUI for the
    quad-engine AI orchestration demo. An operational packet (a COP track
    update, alert, decision request, feed message, or operator note) is
    classified, routed through four advisory reasoning engines, and returned as
    a structured, commander-ready brief.

    Safety doctrine baked into the schema:
      * Every result carries ``human_review_required`` and every decision card
        defaults to ``human_review_required`` status. No field in this contract
        authorizes autonomous kinetic action.
      * ``engine_status`` is reported per engine so commanders can see whether an
        output came from a live local model or a deterministic placeholder.
      * No model paths, R2 credentials, or vault keys are ever surfaced here; the
        GUI only ever sees recommendations / briefs / summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineStatus(str, Enum):
    """Operational status of a single reasoning engine.

    Tactical context:
        ``live_local`` means an on-device GGUF model produced the output;
        ``placeholder`` means a deterministic, doctrine-shaped stand-in was used
        (the demo must never go blank); ``unavailable`` means the engine could
        not contribute at all. The GUI surfaces this so commanders never mistake
        a placeholder for a live model assessment.
    """

    LIVE_LOCAL = "live_local"
    PLACEHOLDER = "placeholder"
    UNAVAILABLE = "unavailable"


class EngineRole(str, Enum):
    """Doctrinal role assigned to each engine in the quad-engine layer."""

    TACTICAL = "tactical"
    REASONING = "reasoning"
    PLANNING = "planning"
    ARABIC = "arabic"


class PacketType(str, Enum):
    """Classification of an inbound operational packet."""

    TRACK_UPDATE = "track_update"
    ALERT = "alert"
    DECISION_REQUEST = "decision_request"
    FEED = "feed"
    OPERATOR_NOTE = "operator_note"


# Canonical engine identifiers used across the module and registry.
TACTICAL_ENGINE = "tactical_engine"
REASONING_ENGINE = "reasoning_engine"
PLANNING_ENGINE = "planning_engine"
ARABIC_ENGINE = "arabic_engine"

ENGINE_IDS: tuple[str, ...] = (
    TACTICAL_ENGINE,
    REASONING_ENGINE,
    PLANNING_ENGINE,
    ARABIC_ENGINE,
)

# Output keys the orchestrator can produce, mapped to their primary engine.
OUTPUT_SITREP = "sitrep"
OUTPUT_THREAT = "threat_assessment"
OUTPUT_COA = "coa_options"
OUTPUT_ARABIC = "arabic_summary"

DEFAULT_REQUESTED_OUTPUTS: tuple[str, ...] = (
    OUTPUT_SITREP,
    OUTPUT_THREAT,
    OUTPUT_COA,
    OUTPUT_ARABIC,
)


class ModelRegistryEntry(BaseModel):
    """Registry record describing one engine and its (optional) local model.

    Security note:
        ``model_file`` is a *bare filename only*; it is resolved against the
        trusted ``S3M_MODELS_DIR`` and is never accepted from user input. This
        prevents path traversal and shell injection into the local runner.
    """

    engine_id: str
    display_name: str
    model_file: str
    role: EngineRole
    status: EngineStatus = EngineStatus.PLACEHOLDER
    max_tokens: int = Field(default=512, ge=1, le=4096)
    description: str = ""


class BackendReadiness(BaseModel):
    """Optional extended readiness for planning backends (Le Chonk staging)."""

    phase: str = ""
    backing_engine_id: str = ""
    precision: str = ""
    runtime: str = ""
    device: str = ""
    fallback_reason: str = ""
    profile: str = ""


class EngineRecord(BaseModel):
    """Public, GUI-safe view of an engine's current status."""

    engine_id: str
    display_name: str
    role: EngineRole
    status: EngineStatus
    model_present: bool = False
    max_tokens: int = 512
    description: str = ""
    backend_readiness: Optional[BackendReadiness] = None


class OperationalPacket(BaseModel):
    """Inbound operational packet submitted for quad-engine orchestration."""

    packet_id: str = Field(..., min_length=1, max_length=128)
    source: str = Field(default="cop", max_length=64)
    track: str = Field(default="saudi_mod", max_length=64)
    packet_type: PacketType = PacketType.TRACK_UPDATE
    classification: str = Field(default="UNCLASSIFIED_DEMO", max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)
    requested_outputs: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REQUESTED_OUTPUTS)
    )


class RouteInfo(BaseModel):
    """Routing decision produced by the packet router."""

    primary_engine: str
    supporting_engines: List[str] = Field(default_factory=list)
    reason: str = ""
    route_hint: str = "tactical"


class DecisionCard(BaseModel):
    """A human-review decision card. Never an autonomous action.

    Tactical context:
        Decision cards are recommendations surfaced to a commander. ``status``
        defaults to ``human_review_required`` and the demo layer never marks a
        card as executed or authorizes kinetic effects.
    """

    title: str
    summary: str
    priority: str = "medium"
    status: str = "human_review_required"
    recommended_action: str = ""


class CoaOption(BaseModel):
    """A single course-of-action option produced by the planning engine."""

    option_id: str
    name: str
    description: str
    risk: str = "medium"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class QuadEngineResult(BaseModel):
    """Structured, commander-ready output returned to S3M-GUI."""

    result_id: str
    packet_id: str
    route: RouteInfo
    outputs: Dict[str, Any] = Field(default_factory=dict)
    decision_cards: List[DecisionCard] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    human_review_required: bool = True
    engine_status: Dict[str, EngineStatus] = Field(default_factory=dict)
    classification: str = "UNCLASSIFIED_DEMO"
    timestamp: str = Field(default_factory=_now_iso)


class OrchestratorStatus(BaseModel):
    """High-level status of the quad-engine orchestration layer."""

    status: str = "operational"
    mode: str = "demo"
    local_llm_enabled: bool = False
    local_llm_available: bool = False
    models_dir: str = ""
    engines: Dict[str, EngineStatus] = Field(default_factory=dict)
    planning_backend: Optional[BackendReadiness] = None
    lechonk_feature_flag: bool = False
    autonomous_action_enabled: bool = False
    human_review_required: bool = True
    external_apis_called: bool = False
    timestamp: str = Field(default_factory=_now_iso)
