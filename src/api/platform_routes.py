"""Shared platform registry for API modules that depend on adapters."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.platforms.fixed.horizon_adapter import HorizonAdapter, TrackStore
from src.platforms.payloads.weapon_adapters import (
    MANPADSAdapter,
    OrionZU23Adapter,
    RCWS127Adapter,
    RCWS145Adapter,
    SICHAdapter,
)

platform_router = APIRouter()


class PlatformRegistry:
    """In-memory registry that exposes tactical platform and payload adapters."""

    def __init__(self) -> None:
        self._platform_adapters: dict[str, Any] = {}
        self._payload_adapters: dict[str, Any] = {}
        self._track_stores: dict[str, TrackStore] = {}

    def register_platform(self, platform_id: str, adapter: Any, track_store: TrackStore | None = None) -> None:
        if not isinstance(platform_id, str) or not platform_id.strip():
            raise ValueError("platform_id must be a non-empty string")
        key = platform_id.strip()
        self._platform_adapters[key] = adapter
        if track_store is not None:
            self._track_stores[key] = track_store

    def register_payload_adapter(self, payload_id: str, adapter: Any) -> None:
        if not isinstance(payload_id, str) or not payload_id.strip():
            raise ValueError("payload_id must be a non-empty string")
        self._payload_adapters[payload_id.strip()] = adapter

    def get_platform_adapter(self, platform_id: str) -> Any | None:
        return self._platform_adapters.get(platform_id)

    def get_payload_adapters(self) -> dict[str, Any]:
        return dict(self._payload_adapters)

    def get_track_store(self, platform_id: str) -> TrackStore | None:
        return self._track_stores.get(platform_id)

    def get_horizon_track_store(self) -> TrackStore:
        store = self.get_track_store("horizon")
        if store is None:
            raise RuntimeError("horizon track store is not registered")
        return store

    def ensure_defaults(self) -> None:
        if "horizon" not in self._platform_adapters:
            horizon = HorizonAdapter(platform_id="horizon-fixed-1")
            horizon.connect()
            self.register_platform("horizon", horizon, track_store=TrackStore())

        # Tactical context: these payloads are the available effectors for engagement recommendations.
        if not self._payload_adapters:
            payloads = {
                "rcws127": RCWS127Adapter(payload_id="rcws127"),
                "rcws145": RCWS145Adapter(payload_id="rcws145"),
                "sich": SICHAdapter(payload_id="sich"),
                "orion_zu23": OrionZU23Adapter(payload_id="orion_zu23"),
                "manpads": MANPADSAdapter(payload_id="manpads"),
            }
            for adapter in payloads.values():
                adapter.connect()
            for payload_id, adapter in payloads.items():
                self.register_payload_adapter(payload_id, adapter)


platform_registry = PlatformRegistry()
platform_registry.ensure_defaults()

