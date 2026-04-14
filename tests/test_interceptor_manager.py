"""Unit tests for fleet interceptor manager behavior."""

from __future__ import annotations

from services.interceptor.interceptor_manager import InterceptorManager
from services.interceptor.models import InterceptorConfig


def _config(interceptor_id: str = "int-1", *, fuel_endurance_s: float = 10.0) -> InterceptorConfig:
    return InterceptorConfig(
        interceptor_id=interceptor_id,
        max_speed_mps=250.0,
        max_acceleration_mps2=30.0,
        seeker_acquisition_range_m=2_000.0,
        hit_radius_m=20.0,
        fuel_endurance_s=fuel_endurance_s,
    )


def test_register_assign_launch_and_guide_cycle() -> None:
    manager = InterceptorManager()
    manager.register_interceptor(_config())

    assert manager.assign_target("int-1", "trk-1") is True
    assert manager.launch("int-1") is True
    assert manager.radar_acquired("int-1") is True

    solution = manager.guide(
        interceptor_id="int-1",
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(10.0, 0.0, 0.0),
        target_pos=(800.0, 0.0, 0.0),
        target_vel=(5.0, 0.0, 0.0),
    )
    assert solution is not None
    assert solution.interceptor_id == "int-1"
    assert solution.target_id == "trk-1"

    active = manager.get_active_interceptions()
    assert len(active) == 1
    assert active[0]["interceptor_id"] == "int-1"
    assert active[0]["target_id"] == "trk-1"
    assert active[0]["cycle"] == 1


def test_unknown_interceptor_operations_return_failure() -> None:
    manager = InterceptorManager()

    assert manager.assign_target("missing", "trk-1") is False
    assert manager.launch("missing") is False
    assert manager.radar_acquired("missing") is False
    assert (
        manager.guide(
            interceptor_id="missing",
            interceptor_pos=(0.0, 0.0, 0.0),
            interceptor_vel=(0.0, 0.0, 0.0),
            target_pos=(1.0, 0.0, 0.0),
            target_vel=(0.0, 0.0, 0.0),
        )
        is None
    )
    assert manager.get_result("missing") is None


def test_get_result_records_completed_intercept_once() -> None:
    manager = InterceptorManager()
    manager.register_interceptor(_config("int-hit"))
    assert manager.assign_target("int-hit", "trk-hit") is True
    assert manager.launch("int-hit") is True
    assert manager.radar_acquired("int-hit") is True

    # Tactical close-range setup forces immediate hit confirmation.
    solution = manager.guide(
        interceptor_id="int-hit",
        interceptor_pos=(100.0, 0.0, 0.0),
        interceptor_vel=(0.0, 0.0, 0.0),
        target_pos=(100.0, 0.0, 0.0),
        target_vel=(0.0, 0.0, 0.0),
    )
    assert solution is not None
    assert solution.should_fire_fuze is True

    result_1 = manager.get_result("int-hit")
    result_2 = manager.get_result("int-hit")
    assert result_1 is not None
    assert result_2 is not None
    assert result_1.outcome == "hit"
    assert result_2.outcome == "hit"

    stats = manager.get_stats()
    assert stats["completed"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 0


def test_miss_updates_stats_after_fuel_exhaustion() -> None:
    manager = InterceptorManager()
    manager.register_interceptor(_config("int-miss", fuel_endurance_s=1.0))
    assert manager.assign_target("int-miss", "trk-miss") is True
    assert manager.launch("int-miss") is True
    assert manager.radar_acquired("int-miss") is True

    solution = manager.guide(
        interceptor_id="int-miss",
        interceptor_pos=(0.0, 0.0, 0.0),
        interceptor_vel=(0.0, 0.0, 0.0),
        target_pos=(5_000.0, 0.0, 0.0),
        target_vel=(0.0, 0.0, 0.0),
    )
    assert solution is not None

    result = manager.get_result("int-miss")
    assert result is not None
    assert result.outcome == "miss"

    stats = manager.get_stats()
    assert stats["completed"] == 1
    assert stats["hits"] == 0
    assert stats["misses"] == 1
