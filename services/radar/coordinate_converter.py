"""Radar coordinate conversion for tactical COP updates."""

from __future__ import annotations

import math

from services.radar.models import RadarConfig, RadarPlot


class CoordinateConverter:
    """Convert radar polar coordinates to Cartesian fusion coordinates."""

    def convert_plot(self, plot: RadarPlot, config: RadarConfig) -> None:
        if not isinstance(plot, RadarPlot):
            raise ValueError("plot must be a RadarPlot")
        if not isinstance(config, RadarConfig):
            raise ValueError("config must be a RadarConfig")

        az = math.radians(plot.azimuth_deg)
        el = math.radians(plot.elevation_deg)
        horizontal = plot.range_m * math.cos(el)

        # Tactical note: preserving local XYZ offsets aligns radar-origin
        # returns with COP fusion grids used by fire-control units.
        x = horizontal * math.cos(az) + config.position_m[0]
        y = horizontal * math.sin(az) + config.position_m[1]
        z = plot.range_m * math.sin(el) + config.position_m[2]
        plot.position_cartesian = (x, y, z)

