"""Core air-defense data models for effector and allocation workflows.

Military context:
These models preserve auditable tactical state for layered interception, so
operators can trace how C2 services assign effectors to hostile tracks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class EffectorCategory(str, Enum):
    """Effector capability families used in layered defense planning."""

    MISSILE = "missile"
    GUN = "gun"
    EW = "ew"


class DefenseEchelon(str, Enum):
    """Layered defensive envelope bands used for interceptor assignment."""

    SHORT_RANGE = "short_range"
    MEDIUM_RANGE = "medium_range"
    LONG_RANGE = "long_range"


class EffectorState(str, Enum):
    """Operational readiness states for engagement-capable effectors."""

    READY = "ready"
    ENGAGING = "engaging"
    RELOADING = "reloading"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


@dataclass
class Effector:
    """Effector record with tactical readiness and fire-control attributes."""

    effector_id: str
    name: str
    category: EffectorCategory
    echelon: DefenseEchelon
    position: Tuple[float, float, float]
    max_range_m: float
    ammunition_capacity: int
    ammunition_remaining: int
    state: EffectorState = EffectorState.READY
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_available(self) -> bool:
        """Return True when the effector can accept a new target tasking."""
        return self.state == EffectorState.READY and self.ammunition_remaining > 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the effector for API responses and audit logs."""
        return {
            "effector_id": self.effector_id,
            "name": self.name,
            "category": self.category.value,
            "echelon": self.echelon.value,
            "position": list(self.position),
            "max_range_m": self.max_range_m,
            "ammunition_capacity": self.ammunition_capacity,
            "ammunition_remaining": self.ammunition_remaining,
            "state": self.state.value,
            "metadata": dict(self.metadata),
        }


@dataclass
class DefenseZone:
    """Circular defensive zone describing tactical area responsibility."""

    zone_id: str
    name: str
    echelon: DefenseEchelon
    center: Tuple[float, float, float]
    radius_m: float
    defended_asset: str
    defended_asset_ar: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize zone geometry and defended asset metadata."""
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "echelon": self.echelon.value,
            "center": list(self.center),
            "radius_m": self.radius_m,
            "defended_asset": self.defended_asset,
            "defended_asset_ar": self.defended_asset_ar,
        }


@dataclass
class AllocationRecord:
    """Audit record representing one target-to-effector assignment decision."""

    allocation_id: str
    target_id: str
    effector_id: str
    target_position: Tuple[float, float, float]
    target_speed_mps: float
    classification: str
    echelon: DefenseEchelon
    score: float
    reasoning: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize allocation details for C2 logs and API clients."""
        return {
            "allocation_id": self.allocation_id,
            "target_id": self.target_id,
            "effector_id": self.effector_id,
            "target_position": list(self.target_position),
            "target_speed_mps": self.target_speed_mps,
            "classification": self.classification,
            "echelon": self.echelon.value,
            "score": self.score,
            "reasoning": self.reasoning,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AllocationDecision:
    """Output object for allocator decisions with operator-facing rationale."""

    allocated: bool
    allocation: Optional[AllocationRecord]
    alternatives_count: int
    echelon_used: Optional[DefenseEchelon]
    reasoning: str

