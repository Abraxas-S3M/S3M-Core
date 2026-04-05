"""G24 USV adapter for tactical maritime maneuver control."""

from __future__ import annotations

from src.platforms.common.messages import PlatformState, PlatformType


class G24Adapter:
    """Offline simulation adapter for an unmanned surface vehicle."""

    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self._connected = False
        self._position = (0.0, 0.0, 0.0)

    def connect(self) -> bool:
        self._connected = True
        return True

    def read_state(self) -> PlatformState:
        return PlatformState(
            platform_id=self.platform_id,
            platform_type=PlatformType.USV,
            position=self._position,
        )
