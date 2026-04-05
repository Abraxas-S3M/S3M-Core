"""Unit tests for platform dashboard provider snapshots."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.platform_provider import PlatformProvider
from src.dashboard.providers.runtime_store import reset_runtime_state, set_agents
from src.platforms.common.messages import PlatformState, PlatformType


class _MockAdapter:
    """Mock platform adapter used to validate tactical snapshot normalization."""

    def read_state(self) -> PlatformState:
        state = PlatformState(
            platform_id="alpha-1",
            platform_type=PlatformType.UGV,
            position=(10.0, 20.0, 0.0),
        )
        state.heading = 135.0
        state.speed = 12.5
        state.health_state = "nominal"
        state.autonomy_mode = "autonomous"
        return state


def setup_function() -> None:
    reset_runtime_state()


def test_platform_provider_uses_registered_adapter_state() -> None:
    provider = PlatformProvider()
    provider.register_adapter("alpha-1", _MockAdapter(), autonomy_level="autonomous")
    snapshot = provider.get_snapshot()
    assert snapshot["provider"] == "platform"
    assert snapshot["platforms"]
    row = snapshot["platforms"][0]
    assert row["platform_id"] == "alpha-1"
    assert row["position"] == (10.0, 20.0, 0.0)
    assert row["heading"] == 135.0
    assert row["speed"] == 12.5
    assert row["health"] == "nominal"
    assert row["autonomy_level"] == "autonomous"


def test_platform_provider_falls_back_to_runtime_agents() -> None:
    set_agents(
        [
            {
                "id": "runtime-1",
                "position": (1.0, 2.0, 3.0),
                "heading": 45.0,
                "speed": 7.0,
                "health": "degraded",
                "autonomy_level": "supervised",
                "capability": "ground",
            }
        ]
    )
    provider = PlatformProvider()
    snapshot = provider.get_snapshot()
    assert snapshot["platforms"]
    row = snapshot["platforms"][0]
    assert row["platform_id"] == "runtime-1"
    assert row["health"] == "degraded"
    assert row["autonomy_level"] == "supervised"
