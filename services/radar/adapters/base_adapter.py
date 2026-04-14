"""Base contract for radar adapter implementations.

Military context:
Every radar family reports with different message formats; this abstract
adapter enforces a common conversion path into validated tactical plots.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from services.radar.models import RadarConfig, RadarPlot


class BaseRadarAdapter(ABC):
    """Common adapter interface used by tactical radar ingest pipelines."""

    def __init__(self, config: RadarConfig | None = None) -> None:
        self.config = config or self.create_default_config()
        if not isinstance(self.config, RadarConfig):
            raise ValueError("config must be RadarConfig")
        if not isinstance(self.config.radar_id, str) or not self.config.radar_id.strip():
            raise ValueError("config.radar_id must be a non-empty string")

    @abstractmethod
    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        """Convert vendor-native data payloads into standardized radar plots."""
        raise NotImplementedError

    @abstractmethod
    def create_default_config(self) -> RadarConfig:
        """Provide baseline tactical settings for a radar family."""
        raise NotImplementedError

