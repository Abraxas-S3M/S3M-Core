#!/usr/bin/env python3
"""Demonstrate full interceptor guidance sequence.

Military context:
Runs an offline command-guidance timeline from launch through 200-300 m
autonomous handoff and terminal engagement declaration.
"""

from __future__ import annotations

import os
import sys
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.interceptor.interceptor_manager import InterceptorManager
from services.interceptor.models import InterceptorConfig

Vector3 = Tuple[float, float, float]


def _advance(position: Vector3, velocity: Vector3, dt_s: float) -> Vector3:
    return (
        position[0] + (velocity[0] * dt_s),
        position[1] + (velocity[1] * dt_s),
        position[2] + (velocity[2] * dt_s),
    )


def main() -> None:
    print("=" * 78)
    print("S3M INTERCEPTOR GUIDANCE DEMO (KRECHET 9C905-2 EQUIVALENT)")
    print("=" * 78)

    config = InterceptorConfig(
        interceptor_type="titan_class",
        name_en="Titan Interceptor",
        name_ar="المعترض تايتان",
        max_speed_mps=78.0,
        max_acceleration_mps2=16.0,
        update_rate_hz=20.0,
        navigation_constant=3.5,
        terminal_approach_range_m=1200.0,
    )
    manager = InterceptorManager()
    interceptor_id = "intc-demo-001"
    target_id = "trk-hostile-001"
    target_position: Vector3 = (2600.0, 0.0, 350.0)
    target_velocity: Vector3 = (-18.0, 3.0, 0.0)
    dt_s = 0.5

    print("\n[1] Register interceptor")
    print(manager.register_interceptor(interceptor_id=interceptor_id, config=config))
    print("\n[2] Launch interceptor")
    print(manager.launch_interceptor(interceptor_id=interceptor_id, takeoff_altitude_m=140.0))

    print("\n[3] Assign target and begin command guidance")
    manager.assign_target(
        interceptor_id=interceptor_id,
        target_id=target_id,
        target_position_m=target_position,
        target_velocity_mps=target_velocity,
        target_classification="hostile_uav",
        request_allocation=False,
    )

    handoff_announced = False
    for tick in range(1, 160):
        target_position = _advance(target_position, target_velocity, dt_s)
        manager.assign_target(
            interceptor_id=interceptor_id,
            target_id=target_id,
            target_position_m=target_position,
            target_velocity_mps=target_velocity,
            target_classification="hostile_uav",
            request_allocation=False,
        )
        solution = manager.guide_interceptor(interceptor_id=interceptor_id, dt_s=dt_s)
        print(
            f"[tick={tick:03d}] phase={solution.phase.value:<20} "
            f"mode={solution.mode.value:<24} range={solution.geometry.range_m:7.1f}m "
            f"closing={solution.geometry.closing_velocity_mps:6.1f}m/s "
            f"miss={solution.geometry.predicted_miss_distance_m:6.1f}m"
        )

        if solution.handoff_recommended and not handoff_announced:
            handoff_announced = True
            print(
                "  -> Handoff window reached (200-300m). "
                "Autonomous terminal seeker should assume control."
            )

        if solution.phase.value in {"engaged", "miss"}:
            break

    result = manager.assess_intercept_result(interceptor_id)
    print("\n[4] Engagement assessment")
    print(
        {
            "state": result.state.value,
            "engagement_range_m": round(result.engagement_range_m, 2),
            "miss_distance_m": round(result.miss_distance_m, 2),
            "details": result.details,
        }
    )
    print("=" * 78)


if __name__ == "__main__":
    main()
