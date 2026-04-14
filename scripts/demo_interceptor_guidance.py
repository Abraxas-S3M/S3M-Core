#!/usr/bin/env python3
"""Demonstrate S3M interceptor guidance — full Krechet 9C905-2 equivalent intercept.

Simulates:
1. Titan interceptor launched against incoming Shahed-class UAV at 10km
2. Radar acquires interceptor, midcourse guidance begins (PN law)
3. Interceptor closes on target, transitioning through phases
4. At 250m, autonomous handoff to onboard seeker
5. Engagement at close range
"""

import math
import sys

sys.path.insert(0, ".")

from services.interceptor.guidance_computer import GuidanceComputer
from services.interceptor.models import HandoffCriteria, InterceptorConfig


def main() -> None:
    print("=" * 72)
    print("S3M INTERCEPTOR GUIDANCE DEMO — KRECHET 9C905-2 EQUIVALENT")
    print("Platform: NVIDIA Jetson AGX Orin 64GB | Mode: AIR-GAPPED")
    print("=" * 72)

    config = InterceptorConfig(
        name_en="Titan Interceptor #1",
        name_ar="طائرة اعتراض تيتان #1",
        platform_type="fixed_wing",
        max_speed_mps=80,
        cruise_speed_mps=55,
        max_acceleration_mps2=15,
        nav_constant=4.0,
        guidance_update_hz=10,
        handoff=HandoffCriteria(handoff_range_m=250, terminal_range_m=500),
        kill_radius_m=5,
    )

    gc = GuidanceComputer(config, "tgt-shahed-01")

    print("\n[1] Target: Shahed-class UAV at (0, 10000, 800), heading south at 55 m/s")
    print(f"    Interceptor: {config.name_en} at (0, 0, 500)")

    # Initial states
    intc_pos = [0.0, 0.0, 500.0]
    intc_vel = [0.0, 70.0, 5.0]
    tgt_pos = [200.0, 10000.0, 800.0]
    tgt_vel = [-5.0, -55.0, -2.0]

    print("\n[2] LAUNCH — interceptor airborne")
    gc.launch()
    print(f"    State: {gc.current_state.value}")

    print("\n[3] RADAR ACQUIRED — interceptor tracked, guidance begins")
    gc.radar_acquired()

    dt = 0.1  # 10 Hz guidance
    last_phase = ""
    for cycle in range(2000):
        sol = gc.update(tuple(intc_pos), tuple(intc_vel), tuple(tgt_pos), tuple(tgt_vel))

        # Print phase transitions
        if sol.phase.value != last_phase:
            print(f"\n    === PHASE: {sol.phase.value.upper()} (cycle {cycle}) ===")
            print(
                f"    Range: {sol.geometry.range_m:.0f}m | "
                f"Closing: {sol.geometry.closing_velocity_mps:.1f} m/s"
            )
            print(
                f"    TGO: {sol.geometry.time_to_intercept_s:.1f}s | "
                f"Miss pred: {sol.geometry.predicted_miss_distance_m:.1f}m"
            )
            last_phase = sol.phase.value

        # Print every 50 cycles
        if cycle % 50 == 0 and cycle > 0:
            print(
                f"    [{cycle:4d}] range={sol.geometry.range_m:7.0f}m "
                f"Vc={sol.geometry.closing_velocity_mps:5.1f} "
                f"miss={sol.geometry.predicted_miss_distance_m:5.1f}m "
                f"hdg={sol.command.commanded_heading_deg:5.1f}° "
                f"a_lat={sol.command.lateral_accel_mps2:+5.2f}"
            )

        # Simple physics simulation
        if sol.command.commanded_position:
            # Steer interceptor toward commanded position
            cx, cy, cz = sol.command.commanded_position
            dx = cx - intc_pos[0]
            dy = cy - intc_pos[1]
            dz = cz - intc_pos[2]
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d > 0.1:
                speed = min(
                    config.max_speed_mps,
                    math.sqrt(intc_vel[0] ** 2 + intc_vel[1] ** 2 + intc_vel[2] ** 2) + 1.0,
                )
                intc_vel = [speed * dx / d, speed * dy / d, speed * dz / d]

        intc_pos[0] += intc_vel[0] * dt
        intc_pos[1] += intc_vel[1] * dt
        intc_pos[2] += intc_vel[2] * dt
        tgt_pos[0] += tgt_vel[0] * dt
        tgt_pos[1] += tgt_vel[1] * dt
        tgt_pos[2] += tgt_vel[2] * dt

        if gc.phase_manager.is_complete:
            break

    result = gc.get_result()
    print(f"\n{'=' * 72}")
    print("INTERCEPT RESULT")
    print(f"  Outcome: {result.outcome.upper()}")
    print(f"  Miss distance: {result.miss_distance_m:.1f}m")
    print(f"  Engagement time: {result.engagement_time_s:.1f}s")
    print(f"  Guidance cycles: {result.guidance_cycles}")
    print(f"  Final phase: {result.final_phase.value}")
    print(f"  Final range: {result.final_range_m:.1f}m")
    if result.abort_reason:
        print(f"  Abort reason: {result.abort_reason}")
    print(f"{'=' * 72}")
    print("Demo complete. Interceptor guidance computer operational.")


if __name__ == "__main__":
    main()
