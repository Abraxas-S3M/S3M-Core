"""Western AESA adapter using normalized generic parser."""

from __future__ import annotations

from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter


class WesternAESAAdapter(Generic3DRadarAdapter):
    """AESA tactical radar integration for panel and rotating variants."""

