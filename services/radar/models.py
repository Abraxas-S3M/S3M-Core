"""Radar plot data models for tactical scan processing.

Military context:
Defines validated radar plot payloads used by per-sensor correlators before
multi-sensor fusion, preserving deterministic offline behavior on edge nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Optional, Tuple
from uuid import uuid4


def _validate_cartesian(position: Optional[Tuple[float, float, float]]) -> Optional[Tuple[float, float, float]]:
    if position is None:
        return None
    if len(position) != 3:
        raise ValueError("position_cartesian must contain exactly three coordinates")
    x, y, z = (float(position[0]), float(position[1]), float(position[2]))
    if not (isfinite(x) and isfinite(y) and isfinite(z)):
        raise ValueError("position_cartesian coordinates must be finite numbers")
    return (x, y, z)


@dataclass
class RadarPlot:
    """Single radar detection plot with optional scan correlation annotation."""

    snr_db: float
    position_cartesian: Optional[Tuple[float, float, float]]
    radial_velocity_mps: float = 0.0
    correlated_track_id: Optional[str] = None
    plot_id: str = field(default_factory=lambda: f"plot-{uuid4().hex[:8]}")

    def __post_init__(self) -> None:
        self.snr_db = float(self.snr_db)
        if not isfinite(self.snr_db):
            raise ValueError("snr_db must be a finite number")
        self.position_cartesian = _validate_cartesian(self.position_cartesian)
        self.radial_velocity_mps = float(self.radial_velocity_mps)
        if not isfinite(self.radial_velocity_mps):
            raise ValueError("radial_velocity_mps must be a finite number")
        if self.correlated_track_id is not None and not str(self.correlated_track_id).strip():
            raise ValueError("correlated_track_id must be non-empty when provided")
