"""Base contract for radar feed adapters.

Military context:
Adapter implementations normalize heterogeneous radar payloads into a common
plot schema so C2 workflows can fuse detections across sensors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.radar.models import RadarConfig


class BaseRadarAdapter(ABC):
    """Abstract adapter for radar feed normalization."""

    def __init__(self, config: RadarConfig | None = None) -> None:
        self.config = config or self.create_default_config()

    @abstractmethod
    def parse_raw_data(self, raw_data: dict[str, Any]) -> list[Any]:
        """Parse inbound feed payload into one or more radar plot objects."""

    @abstractmethod
    def create_default_config(self) -> RadarConfig:
        """Create default configuration for this adapter implementation."""
