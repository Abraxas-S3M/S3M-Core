"""HMMWV unmanned-ground adapter for tactical mobility control."""

from __future__ import annotations

from src.platforms.common.messages import PlatformState, PlatformType


class HMMWVAdapter:
    """Offline simulation adapter for a wheeled UGV platform."""

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
            platform_type=PlatformType.UGV,
            position=self._position,
        )
