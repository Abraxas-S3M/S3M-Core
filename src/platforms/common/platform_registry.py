"""Platform adapter registry for HOOL fleet orchestration.

This registry maintains a validated inventory of configured platforms so mission
control can bind tactics, safety policy, and telemetry polling to known assets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import PlatformAdapter


@dataclass(frozen=True)
class RegisteredPlatform:
    """Metadata for one registered platform adapter."""

    platform_id: str
    platform_type: str
    adapter_class: str
    initial_position: tuple[float, float, float]


class PlatformRegistry:
    """In-memory platform adapter registry used by HOOL startup flows."""

    def __init__(self) -> None:
        self._adapters: dict[str, PlatformAdapter] = {}
        self._metadata: dict[str, RegisteredPlatform] = {}

    def register_adapter(
        self,
        *,
        platform_id: str,
        platform_type: str,
        adapter_class: str,
        adapter: PlatformAdapter,
        initial_position: tuple[float, float, float],
    ) -> None:
        if not isinstance(platform_id, str) or not platform_id.strip():
            raise ValueError("platform_id must be a non-empty string")
        if not isinstance(platform_type, str) or not platform_type.strip():
            raise ValueError("platform_type must be a non-empty string")
        if not isinstance(adapter_class, str) or not adapter_class.strip():
            raise ValueError("adapter_class must be a non-empty string")
        if len(initial_position) != 3:
            raise ValueError("initial_position must be a 3D tuple")
        if not hasattr(adapter, "connect") or not hasattr(adapter, "read_state"):
            raise TypeError("adapter must expose connect() and read_state()")

        normalized_id = platform_id.strip()
        self._adapters[normalized_id] = adapter
        self._metadata[normalized_id] = RegisteredPlatform(
            platform_id=normalized_id,
            platform_type=platform_type.strip().lower(),
            adapter_class=adapter_class.strip(),
            initial_position=(
                float(initial_position[0]),
                float(initial_position[1]),
                float(initial_position[2]),
            ),
        )

    def get_adapter(self, platform_id: str) -> PlatformAdapter:
        if platform_id not in self._adapters:
            raise KeyError(f"platform is not registered: {platform_id}")
        return self._adapters[platform_id]

    def adapters(self) -> dict[str, PlatformAdapter]:
        return dict(self._adapters)

    def metadata(self) -> dict[str, RegisteredPlatform]:
        return dict(self._metadata)

    def list_platforms(self) -> list[RegisteredPlatform]:
        return [self._metadata[key] for key in sorted(self._metadata)]

    def fleet_status_summary(self) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        for platform_id in sorted(self._adapters):
            record = self._metadata[platform_id]
            adapter = self._adapters[platform_id]
            try:
                state = adapter.read_state()
                position = tuple(getattr(state, "position", record.initial_position))
                health_state = str(getattr(getattr(state, "health_state", None), "value", "unknown"))
                summary.append(
                    {
                        "platform_id": platform_id,
                        "type": record.platform_type,
                        "adapter_class": record.adapter_class,
                        "position": position,
                        "health_state": health_state,
                    }
                )
            except Exception as exc:
                summary.append(
                    {
                        "platform_id": platform_id,
                        "type": record.platform_type,
                        "adapter_class": record.adapter_class,
                        "position": record.initial_position,
                        "health_state": "unknown",
                        "error": str(exc),
                    }
                )
        return summary
