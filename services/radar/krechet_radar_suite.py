"""Krechet-equivalent multi-radar suite templates.

Military context:
Defines a layered sensor composition where long-range AESA cuing is handed to
medium and short range radars for resilient local air picture continuity.
"""

from __future__ import annotations

from typing import Sequence

from services.radar.models import RadarConfig, RadarType
from services.radar.radar_manager import RadarManager


def create_krechet_radar_suite(
    manager: RadarManager,
    *,
    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Sequence[RadarConfig]:
    """Register and return a three-radar Krechet-equivalent sensor package."""
    suite = [
        RadarConfig(
            radar_id="krechet-rps-82-1",
            name_en="RPS-82 Short-Range Radar",
            radar_type=RadarType.RPS_82,
            position=center,
            max_range_m=12_000.0,
        ),
        RadarConfig(
            radar_id="krechet-rps-202-1",
            name_en="RPS-202 Medium-Range Radar",
            radar_type=RadarType.RPS_202,
            position=center,
            max_range_m=18_000.0,
        ),
        RadarConfig(
            radar_id="krechet-aesa-1",
            name_en="Krechet AESA Radar",
            radar_type=RadarType.AESA,
            position=center,
            max_range_m=45_000.0,
        ),
    ]
    for radar in suite:
        manager.register_radar(radar, replace_existing=True)
    return suite
