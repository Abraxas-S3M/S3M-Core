"""Platform registry routes and shared adapter references.

Tactical context:
This module centralizes platform and track-store handles so autonomy routes can
read state and issue mobility directives without external network dependencies.
"""

from __future__ import annotations

from threading import RLock
from typing import Dict

from fastapi import APIRouter

from src.platforms.common.contracts import PlatformAdapter
from src.platforms.fixed.horizon_adapter import HorizonAdapter, TrackStore
from src.platforms.uav.warwar_adapter import WarWarAdapter
from src.platforms.ugv.hmmwv_adapter import HMMWVAdapter
from src.platforms.usv.g24_adapter import G24Adapter


platform_router = APIRouter()


class PlatformRegistry:
    """In-memory adapter registry used by offline mission-control routes."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._platforms: Dict[str, PlatformAdapter] = {}
        self._track_store = TrackStore()
        self._horizon_adapter = HorizonAdapter("horizon-fixed-1")

        self.register_platform(self._horizon_adapter.platform_id, self._horizon_adapter)
        self._register_default_mobile_platforms()

    def register_platform(self, platform_id: str, adapter: PlatformAdapter) -> None:
        if not platform_id:
            raise ValueError("platform_id must be non-empty")
        connected = adapter.connect()
        if not connected:
            raise RuntimeError(f"failed to connect platform adapter: {platform_id}")
        with self._lock:
            self._platforms[platform_id] = adapter

    def get_platform(self, platform_id: str) -> PlatformAdapter | None:
        with self._lock:
            return self._platforms.get(platform_id)

    def list_platform_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._platforms.keys())

    def get_track_store(self) -> TrackStore:
        return self._track_store

    def get_horizon_adapter(self) -> HorizonAdapter:
        return self._horizon_adapter

    def _register_default_mobile_platforms(self) -> None:
        # Seed representative platforms so command teams can start smoke
        # missions immediately in disconnected tactical exercises.
        defaults: Dict[str, PlatformAdapter] = {
            "hmmwv-1": HMMWVAdapter("hmmwv-1"),
            "warwar-1": WarWarAdapter("warwar-1"),
            "g24-1": G24Adapter("g24-1"),
        }
        for platform_id, adapter in defaults.items():
            self.register_platform(platform_id, adapter)


platform_registry = PlatformRegistry()


@platform_router.get("/api/platforms")
async def list_platforms() -> dict[str, list[str]]:
    """List known platform identifiers available for mission assignment."""
    return {"platform_ids": platform_registry.list_platform_ids()}
