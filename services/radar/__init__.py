"""Radar plot preprocessing and scan correlation services.

Military context:
Maintains per-radar scan-to-scan custody so downstream fusion receives
stable, physically plausible plot groupings under contested conditions.
"""

from services.radar.models import RadarPlot
from services.radar.plot_correlator import PlotCorrelator

__all__ = ["RadarPlot", "PlotCorrelator"]
