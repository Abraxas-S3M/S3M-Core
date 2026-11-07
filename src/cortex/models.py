"""Validated models for mission bindings and PCCP quarantine proposals."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class BindingSource(str, Enum):
    """Trusted origins for mission bindings — never accept untrusted NLP text."""

    OPERATOR = "operator"
    MISSION_PLANNER = "mission_planner"


class MissionFlow(BaseModel):
    """A directed mission dependency between two twin nodes."""

    source: str = Field(min_length=1, max_length=128)
    destination: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=256)

    @field_validator("source", "destination", "purpose")
    @classmethod
    def _reject_control_chars(cls, value: str) -> str:
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("flow fields must not contain control characters")
        return value.strip()


class MissionBinding(BaseModel):
    """Mission-to-flow association with priority and operational time window."""

    mission_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    priority: int = Field(ge=1, le=5)
    window_start: str
    window_end: str
    flows: List[MissionFlow] = Field(min_length=1)
    source: BindingSource
    partition: str = "default"
    active: bool = False

    @field_validator("mission_id", "name", "partition")
    @classmethod
    def _strip_safe(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must be non-empty")
        return cleaned


class NetworkEdge(BaseModel):
    """Graph edge in the Cortex twin with baseline disruption cost."""

    edge_id: str
    source: str
    destination: str
    purpose: str = ""
    partition: str = "default"
    disruption_cost: float = Field(default=1.0, ge=0.0)


class PCCPChange(BaseModel):
    """Partition Connection Control Policy change — narrow or allow flows."""

    action: str  # "narrow" | "allow"
    edge_id: str
    partition: str
    rationale: str = ""


class MinimalProfilePlan(BaseModel):
    """Quarantine proposal for a suspect node under active mission constraints."""

    node: str
    keep_edges: List[str] = Field(default_factory=list)
    narrow_edges: List[PCCPChange] = Field(default_factory=list)
    escalates_to_human: bool = False
    reason: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _coherent_escalation(self) -> "MinimalProfilePlan":
        if self.escalates_to_human and not self.reason:
            self.reason = "minimal mission-preserving profile impossible"
        return self
