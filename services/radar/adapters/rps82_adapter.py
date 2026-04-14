"""RPS-82 adapter using normalized generic parser."""

from __future__ import annotations

from services.radar.adapters.generic_3d_radar import Generic3DRadarAdapter


class RPS82Adapter(Generic3DRadarAdapter):
    """RPS-82 tactical radar integration."""

