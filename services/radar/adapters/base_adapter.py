"""Base adapter contract for tactical radar integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from services.radar.models import RadarConfig, RadarPlot


class BaseRadarAdapter(ABC):
    """Base parser/filter contract for radar vendor payloads."""

    def __init__(self, config: RadarConfig) -> None:
        if not isinstance(config, RadarConfig):
            raise ValueError("config must be a RadarConfig")
        self.config = config

    @abstractmethod
    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        """Parse vendor payload into normalized radar plots."""

    def filter_clutter(self, plots: List[RadarPlot]) -> List[RadarPlot]:
        """Drop low-SNR plots to reduce clutter in tactical COP feeds."""
        if not isinstance(plots, list):
            raise ValueError("plots must be a list")
        min_snr = self.config.clutter_snr_threshold_db
        return [plot for plot in plots if isinstance(plot, RadarPlot) and plot.snr_db >= min_snr]

