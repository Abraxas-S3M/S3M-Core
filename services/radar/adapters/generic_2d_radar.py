"""Generic 2D radar adapter for azimuth/range tactical sensors."""

from __future__ import annotations

from typing import Any, Dict, List

from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter
from services.radar.models import RadarPlot


class Generic2DRadarAdapter(Generic3DRadarAdapter):
    """Normalizes 2D payloads and forces zero elevation."""

    def parse_raw_data(self, raw_data: Dict[str, Any]) -> List[RadarPlot]:
        plots = super().parse_raw_data(raw_data)
        for plot in plots:
            plot.elevation_deg = 0.0
        return plots

