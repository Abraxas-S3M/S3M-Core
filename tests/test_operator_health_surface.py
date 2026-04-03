"""Unit tests for operator health surface aggregation."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.edge_runtime.health_surface import OperatorHealthSurface


class _EnumLike:
    def __init__(self, value: str) -> None:
        self.value = value


@dataclass
class _Policy:
    description: str
    max_concurrent_models: int
    allow_gpu: bool
    allow_large_transfers: bool
    summarization_interval_sec: int


@dataclass
class _Profile:
    tier: _EnumLike
    cpu_cores: int
    ram_available_gb: float
    gpu_detected: bool
    thermal_zone_c: float


class _Profiler:
    def __init__(self, profile: _Profile | None) -> None:
        self.profile = profile


class _Controller:
    def __init__(self, mode: str, transitions: list[dict[str, str]]) -> None:
        self.current_mode = _EnumLike(mode)
        self._transitions = transitions

    def current_policy(self) -> _Policy:
        return _Policy(
            description="thermally constrained compute posture",
            max_concurrent_models=2,
            allow_gpu=False,
            allow_large_transfers=False,
            summarization_interval_sec=60,
        )

    def get_transition_log(self) -> list[dict[str, str]]:
        return self._transitions


class _Broker:
    def __init__(self, bearers: list[dict[str, str]]) -> None:
        self._bearers = bearers

    def any_bearer_up(self) -> bool:
        return any(item["state"] in ("up", "degraded") for item in self._bearers)

    def bearer_status(self) -> list[dict[str, str]]:
        return self._bearers


class _Queue:
    def __init__(self, pending: int) -> None:
        self._pending = pending

    def stats(self) -> dict[str, int]:
        return {"pending": self._pending, "dropped": 1}

    def pending_count(self) -> int:
        return self._pending


def test_full_status_with_profile_includes_expected_fields() -> None:
    profile = _Profile(
        tier=_EnumLike("tactical"),
        cpu_cores=12,
        ram_available_gb=27.556,
        gpu_detected=True,
        thermal_zone_c=64.2,
    )
    transitions = [{"to": f"mode-{idx}"} for idx in range(15)]
    surface = OperatorHealthSurface(
        profiler=_Profiler(profile=profile),
        controller=_Controller(mode="degraded", transitions=transitions),
        broker=_Broker(
            bearers=[
                {"name": "lte", "state": "up"},
                {"name": "satcom", "state": "degraded"},
                {"name": "wifi", "state": "down"},
            ]
        ),
        queue=_Queue(pending=4),
    )

    payload = surface.full_status()

    timestamp = datetime.fromisoformat(payload["timestamp"])
    assert timestamp.tzinfo is not None
    assert payload["node"] == {
        "tier": "tactical",
        "cpu_cores": 12,
        "ram_available_gb": 27.56,
        "gpu_detected": True,
        "thermal_c": 64.2,
    }
    assert payload["operating_mode"] == {
        "mode": "degraded",
        "description": "thermally constrained compute posture",
        "max_concurrent_models": 2,
        "gpu_allowed": False,
        "large_transfers_allowed": False,
        "summarization_interval_sec": 60,
    }
    assert payload["communications"]["any_bearer_up"] is True
    assert len(payload["communications"]["bearers"]) == 3
    assert payload["queue"] == {"pending": 4, "dropped": 1}
    assert len(payload["transitions"]) == 10
    assert payload["transitions"][0] == {"to": "mode-5"}


def test_full_status_without_profile_uses_safe_defaults() -> None:
    surface = OperatorHealthSurface(
        profiler=_Profiler(profile=None),
        controller=_Controller(mode="nominal", transitions=[]),
        broker=_Broker(bearers=[]),
        queue=_Queue(pending=0),
    )

    payload = surface.full_status()
    assert payload["node"] == {
        "tier": "unknown",
        "cpu_cores": 0,
        "ram_available_gb": 0,
        "gpu_detected": False,
        "thermal_c": None,
    }


def test_summary_line_counts_only_up_and_degraded_bearers() -> None:
    surface = OperatorHealthSurface(
        profiler=_Profiler(profile=None),
        controller=_Controller(mode="recovery", transitions=[]),
        broker=_Broker(
            bearers=[
                {"name": "mesh", "state": "up"},
                {"name": "lte", "state": "degraded"},
                {"name": "wifi", "state": "down"},
            ]
        ),
        queue=_Queue(pending=9),
    )

    assert surface.summary_line() == "[recovery] bearers=2 queued=9"


def test_constructor_rejects_none_dependencies() -> None:
    good_profiler = _Profiler(profile=None)
    good_controller = _Controller(mode="nominal", transitions=[])
    good_broker = _Broker(bearers=[])
    good_queue = _Queue(pending=0)

    for profiler, controller, broker, queue in [
        (None, good_controller, good_broker, good_queue),
        (good_profiler, None, good_broker, good_queue),
        (good_profiler, good_controller, None, good_queue),
        (good_profiler, good_controller, good_broker, None),
    ]:
        try:
            OperatorHealthSurface(
                profiler=profiler,  # type: ignore[arg-type]
                controller=controller,  # type: ignore[arg-type]
                broker=broker,  # type: ignore[arg-type]
                queue=queue,  # type: ignore[arg-type]
            )
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass
