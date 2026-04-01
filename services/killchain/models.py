"""Core data models for autonomous kill-chain operations.

Military context:
These models provide auditable state for safety-critical targeting and
engagement decisions across F2T2EA phases with human-veto compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EngagementAuthority(Enum):
    """Graduated authority levels for autonomous engagement actions."""

    HITL = 1
    HOTL = 2
    SUPERVISED = 3
    DEFENSIVE = 4
    FULL_AUTONOMOUS = 5


class KillChainPhase(str, Enum):
    """F2T2EA phase taxonomy for kill-chain workflow tracing."""

    FIND = "find"
    FIX = "fix"
    TRACK = "track"
    TARGET = "target"
    ENGAGE = "engage"
    ASSESS = "assess"


@dataclass
class TargetClassification:
    """Tracked target hypothesis produced during find/fix/track phases."""

    target_id: str
    classification: str
    confidence: float
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    source: str
    first_detected: datetime
    last_updated: datetime
    track_id: str
    is_military_objective: Optional[bool]
    civilian_proximity_m: float
    collateral_risk: str
    image_evidence: Optional[str]


@dataclass
class EngagementRequest:
    """Engagement authorization object spanning AI and human approval states."""

    request_id: str
    target_id: str
    authority_level: EngagementAuthority
    roe_level: str
    weapon_type: str
    platform_id: str
    requesting_agent: str
    phase: KillChainPhase
    confidence: float
    threat_assessment: str
    collateral_estimate: str
    roe_compliant: bool
    xai_explanation: str
    human_approval_required: bool
    human_approval_timeout_seconds: float
    human_decision: Optional[str]
    human_decision_by: Optional[str]
    human_decision_at: Optional[datetime]
    status: str
    created_at: datetime


@dataclass
class BattleDamageAssessment:
    """Post-engagement battle damage assessment with confidence metadata."""

    bda_id: str
    engagement_request_id: str
    target_id: str
    assessment_time: datetime
    target_status: str
    confidence: float
    method: str
    evidence: List[dict]
    reengagement_recommended: bool
    llm_analysis: Optional[str]


@dataclass
class KillChainAuditEntry:
    """Audit record used for legal traceability of engagement decisions."""

    entry_id: str
    timestamp: datetime
    engagement_request_id: str
    phase: KillChainPhase
    authority_level: EngagementAuthority
    decision: str
    xai_explanation: str
    human_involved: bool
    details: Dict[str, Any] = field(default_factory=dict)
