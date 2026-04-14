"""Data models for interceptor guidance orchestration.

Military context:
These models capture interceptor state transitions from launch to terminal
handoff so offline command-post simulations can audit each engagement step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Dict, Tuple


def _validate_non_empty_text(value: Any, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string")
    return text


def _validate_finite(value: Any, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


def _validate_positive(value: Any, *, field_name: str) -> float:
    parsed = _validate_finite(value, field_name=field_name)
    if parsed <= 0.0:
        raise ValueError(f"{field_name} must be > 0")
    return parsed


def _validate_vec3(value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must be [x_m, y_m, z_m]")
    return (
        _validate_finite(value[0], field_name=f"{field_name}[0]"),
        _validate_finite(value[1], field_name=f"{field_name}[1]"),
        _validate_finite(value[2], field_name=f"{field_name}[2]"),
    )


@dataclass
class HandoffCriteria:
    handoff_range_m: float = 250.0
    terminal_range_m: float = 500.0

    def __post_init__(self) -> None:
        self.handoff_range_m = _validate_positive(self.handoff_range_m, field_name="handoff_range_m")
        self.terminal_range_m = _validate_positive(self.terminal_range_m, field_name="terminal_range_m")
        if self.terminal_range_m < self.handoff_range_m:
            raise ValueError("terminal_range_m must be >= handoff_range_m")


@dataclass
class InterceptorConfig:
    name_en: str = "Interceptor"
    name_ar: str = "طائرة اعتراض"
    platform_type: str = "fixed_wing"
    max_speed_mps: float = 80.0
    nav_constant: float = 4.0
    guidance_update_hz: float = 10.0
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    handoff: HandoffCriteria = field(default_factory=HandoffCriteria)

    def __post_init__(self) -> None:
        self.name_en = _validate_non_empty_text(self.name_en, field_name="name_en")
        self.name_ar = _validate_non_empty_text(self.name_ar, field_name="name_ar")
        self.platform_type = _validate_non_empty_text(self.platform_type, field_name="platform_type")
        self.max_speed_mps = _validate_positive(self.max_speed_mps, field_name="max_speed_mps")
        self.nav_constant = _validate_positive(self.nav_constant, field_name="nav_constant")
        self.guidance_update_hz = _validate_positive(self.guidance_update_hz, field_name="guidance_update_hz")
        self.position = _validate_vec3(self.position, field_name="position")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "platform_type": self.platform_type,
            "max_speed_mps": self.max_speed_mps,
            "nav_constant": self.nav_constant,
            "guidance_update_hz": self.guidance_update_hz,
            "position": list(self.position),
            "handoff": {
                "handoff_range_m": self.handoff.handoff_range_m,
                "terminal_range_m": self.handoff.terminal_range_m,
            },
        }


@dataclass
class InterceptorUnit:
    interceptor_id: str
    config: InterceptorConfig
    assigned_target_id: str | None = None
    launched: bool = False
    radar_acquired: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.interceptor_id = _validate_non_empty_text(self.interceptor_id, field_name="interceptor_id")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interceptor_id": self.interceptor_id,
            "assigned_target_id": self.assigned_target_id,
            "launched": self.launched,
            "radar_acquired": self.radar_acquired,
            "created_at": self.created_at.isoformat(),
            "config": self.config.to_dict(),
        }


@dataclass
class GuidanceSolution:
    interceptor_id: str
    target_id: str
    guidance_mode: str
    command_vector_mps2: Tuple[float, float, float]
    range_to_target_m: float
    closing_speed_mps: float
    handoff_initiated: bool
    terminal_phase: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interceptor_id": self.interceptor_id,
            "target_id": self.target_id,
            "guidance_mode": self.guidance_mode,
            "command_vector_mps2": list(self.command_vector_mps2),
            "range_to_target_m": self.range_to_target_m,
            "closing_speed_mps": self.closing_speed_mps,
            "handoff_initiated": self.handoff_initiated,
            "terminal_phase": self.terminal_phase,
        }


@dataclass
class InterceptionResult:
    interceptor_id: str
    target_id: str
    status: str
    outcome: str
    final_range_m: float
    engagement_time_s: float

