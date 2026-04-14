"""Base primitives for tactical radar adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from services.radar.models import RadarConfig, RadarPlot


class BaseRadarAdapter(ABC):
    """Common base class for radar-specific raw plot adapters."""

    def __init__(self, radar_id: Optional[str] = None, config: Optional[RadarConfig] = None) -> None:
        effective_config = config if config is not None else self.create_default_config()
        if radar_id is not None:
            if not isinstance(radar_id, str) or not radar_id.strip():
                raise ValueError("radar_id must be a non-empty string")
            effective_config.radar_id = radar_id.strip()
        elif not effective_config.radar_id:
            effective_config.radar_id = self.__class__.__name__.replace("Adapter", "").lower()
        self.config = effective_config

    @abstractmethod
    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        """Convert vendor-native payloads into normalized radar plots."""

    @abstractmethod
    def create_default_config(self) -> RadarConfig:
        """Return baseline configuration for this radar family."""
