"""Base abstractions for tactical radar adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.radar.models import RadarConfig, RadarPlot


class BaseRadarAdapter(ABC):
    """Defines a secure interface for normalizing raw radar plots."""

    def __init__(self, config: RadarConfig | None = None) -> None:
        self.config = config or self.create_default_config()

    @abstractmethod
    def parse_raw_data(self, raw_data: dict[str, Any]) -> list[RadarPlot]:
        """Parse untrusted sensor data into validated radar plots."""

    @abstractmethod
    def create_default_config(self) -> RadarConfig:
        """Return a mission-safe default radar configuration."""
