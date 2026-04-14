"""Base adapter contract for tactical radar data normalization.

Military context:
Radar adapters convert platform-specific telemetry into a unified plot model
so downstream air-defense correlation and weapon assignment remain deterministic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.radar.models import RadarConfig, RadarPlot


class BaseRadarAdapter(ABC):
    """Abstract base class for all radar ingest adapters."""

    def __init__(self, config: RadarConfig | None = None) -> None:
        default_config = self.create_default_config()
        if config is None:
            self.config = default_config
        else:
            self.config = config
            if not self.config.radar_id:
                # Preserve tactical traceability by ensuring every plot has a stable source ID.
                self.config.radar_id = default_config.radar_id

    @abstractmethod
    def parse_raw_data(self, raw_data: dict[str, Any]) -> list[RadarPlot]:
        """Parse native sensor payloads into normalized radar plots."""

    @abstractmethod
    def create_default_config(self) -> RadarConfig:
        """Return default sensor configuration used for this adapter family."""
