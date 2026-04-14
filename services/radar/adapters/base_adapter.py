"""Abstract base class for radar type adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from services.radar.models import RadarConfig, RadarPlot


class BaseRadarAdapter(ABC):
    """Abstract adapter that converts radar-specific data into standardized plots."""

    def __init__(self, config: RadarConfig) -> None:
        self.config = config

    @abstractmethod
    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        """Parse radar-specific raw data format into standardized RadarPlots."""

    @abstractmethod
    def create_default_config(self) -> RadarConfig:
        """Return a default configuration for this radar type."""

    def validate_plot(self, plot: RadarPlot) -> bool:
        """Check if a plot falls within this radar's detection limits."""
        if plot.range_m < self.config.min_range_m or plot.range_m > self.config.max_range_m:
            return False
        if self.config.has_elevation:
            if (
                plot.elevation_deg < self.config.min_elevation_deg
                or plot.elevation_deg > self.config.max_elevation_deg
            ):
                return False
        # Tactical cueing rejects weak returns to prevent false engagements.
        if plot.snr_db < self.config.min_detectable_snr_db:
            return False
        return True

    def filter_clutter(self, plots: List[RadarPlot]) -> List[RadarPlot]:
        """Remove plots likely to be clutter based on radar-specific rules."""
        return [p for p in plots if self.validate_plot(p)]
