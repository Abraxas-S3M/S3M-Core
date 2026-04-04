"""Schema models for GUI decision and risk workspaces.

These payloads are optimized for command-post dashboards where operators
need compact, validated tactical summaries.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DecisionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    STEADY = "steady"


class GUIDecision(BaseModel):
    id: str
    title: str
    risk: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    description: str
    status: DecisionStatus
    severity: SeverityLevel
    updatedAt: str


class GUIRiskDomain(BaseModel):
    domain: str
    score: int = Field(ge=0, le=100)
    trend: TrendDirection


class GUIRiskForecast(BaseModel):
    timestamp: str
    score: int = Field(ge=0, le=100)


class GUIRiskDriver(BaseModel):
    name: str
    impact: float = Field(ge=0.0, le=1.0)
    direction: str


class GUIRiskData(BaseModel):
    composite: int = Field(ge=0, le=100)
    domains: List[GUIRiskDomain]
    forecast: List[GUIRiskForecast]
    drivers: List[GUIRiskDriver]
    updatedAt: str


class GUIEnvelope(BaseModel):
    """Common envelope used by GUI workspace adapters."""

    type: str
    payload: Dict[str, Any]
    timestamp: str


class WorkspaceLink(BaseModel):
    """Pointer that allows the GUI to deep-link into a mission workspace."""

    workspace: str
    resourceId: Optional[str] = None
