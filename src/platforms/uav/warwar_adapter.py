"""WarWar UAV adapter for tactical air platform control."""

from __future__ import annotations

from src.platforms.common.messages import PlatformState, PlatformType


class WarWarAdapter:
    """Offline simulation adapter for a quadrotor UAV."""

    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self._connected = False
        self._launched = False
        self._position = (0.0, 0.0, 10.0)

    def connect(self) -> bool:
        self._connected = True
        return True

    def launch(self) -> bool:
        if not self._connected:
            return False
        self._launched = True
        return True

    def read_state(self) -> PlatformState:
        return PlatformState(
            platform_id=self.platform_id,
            platform_type=PlatformType.UAV,
            position=self._position,
        )
