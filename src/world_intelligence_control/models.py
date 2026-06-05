"""Typed models for controlled World Intelligence runtime routing.

Military/tactical context:
These models define explicit operating modes so command dashboards can
maintain intelligence continuity without allowing uncontrolled data flows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def now_iso() -> str:
    """Return UTC timestamp for tactical audit visibility."""
    return datetime.now(timezone.utc).isoformat()


class WorldIntelligenceMode(str, Enum):
    """Operator-selectable runtime mode."""

    LOCAL_SELF_HOSTED = "local_self_hosted"
    EXTERNAL_LIVE_FALLBACK = "external_live_fallback"
    TRAINING_SAFE = "training_safe"
    OFFLINE_SAFE = "offline_safe"


class WorldIntelligenceSource(str, Enum):
    """Resolved data source currently serving command traffic."""

    LOCAL_SELF_HOSTED = "local_self_hosted"
    EXTERNAL_LIVE_FALLBACK = "external_live_fallback"
    OFFLINE_SAFE = "offline_safe"


class ServiceActionResult(BaseModel):
    """Result of local runtime control action."""

    ok: bool
    action: str
    service: str
    detail: str = ""
    timestamp: str = Field(default_factory=now_iso)


class LocalRuntimeHealth(BaseModel):
    """Health state of the local Hetzner World Intelligence runtime."""

    healthy: bool
    status: str
    endpoint: str
    status_code: int | None = None
    detail: str = ""
    checked_at: str = Field(default_factory=now_iso)


class SourceDecision(BaseModel):
    """Resolved source decision used by route handlers."""

    mode: WorldIntelligenceMode
    source: WorldIntelligenceSource
    reason: str
    local_runtime_healthy: bool
    local_runtime_health_url: str | None = None
    fallback_available: bool
    training_safe: bool
    checked_at: str = Field(default_factory=now_iso)


class WorldIntelligenceStatus(BaseModel):
    """Operational status payload for GUI and operators."""

    service: str
    mode: WorldIntelligenceMode
    active_source: WorldIntelligenceSource
    reason: str
    configured_local_url: str
    local_runtime_healthy: bool
    systemd_control_available: bool
    local_runtime: LocalRuntimeHealth
    fallback_available: bool
    training_safe: bool
    fallback_enabled: bool
    timestamp: str = Field(default_factory=now_iso)


class FallbackPayload(BaseModel):
    """Bounded read-only fallback response payload."""

    source: WorldIntelligenceSource = WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK
    status: str
    upstream_url: str | None = None
    upstream_status: int | None = None
    data: Any = None
    detail: str = ""
    timestamp: str = Field(default_factory=now_iso)
