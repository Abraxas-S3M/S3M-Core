#!/usr/bin/env python3
"""Demonstrate S3M air defense — full allocate-engage-miss-reallocate cycle.

Simulates a Krechet-equivalent engagement sequence:
1. Set up a full Saudi air defense unit with echeloned zones.
2. Incoming enemy UAV detected at 35km.
3. Allocator assigns interceptor drone (extended echelon).
4. Interceptor misses — target moves to 12km.
5. Miss handler re-allocates to short-range SAM.
6. SAM engages and confirms kill.
"""

import sys

sys.path.insert(0, ".")

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.saudi_templates import create_krechet_equivalent_unit
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import ZoneManager


def main() -> None:
    print("=" * 70)
    print("S3M AIR DEFENSE DEMO — KRECHET-EQUIVALENT ENGAGEMENT CYCLE")
    print("Platform: NVIDIA Jetson AGX Orin 64GB | Mode: AIR-GAPPED")
    print("=" * 70)

    # Step 1: Set up the air defense unit
    print("\n[1] Setting up Krechet-equivalent air defense unit...")
    registry = EffectorRegistry()
    zone_mgr = ZoneManager()
    unit = create_krechet_equivalent_unit(
        registry,
        zone_mgr,
        center=(0, 0, 0),
        defended_asset="ARAMCO Refinery Complex",
        defended_asset_ar="مجمع تكرير أرامكو",
    )
    stats = registry.get_stats()
    print(f"  Unit: {unit.name_en}")
    print(f"  Effectors: {stats['total']} total, {stats['ready']} ready")
    print(f"  Zones: {len(unit.zone_ids)} echelons")
    coverage = zone_mgr.get_coverage_report()
    for ech, data in coverage.items():
        print(
            f"    {ech}: {data['total_effectors']} effectors, "
            f"{data['outer_radius_m'] / 1000:.0f}km outer range"
        )

    # Step 2: Incoming threat detected
    print("\n[2] THREAT DETECTED: Enemy UAV at 35km, altitude 2000m, speed 80 m/s")
    target_pos = (35000.0, 0.0, 2000.0)
    target_speed = 80.0

    allocator = TargetAllocator(registry, zone_mgr)
    miss_handler = MissHandler(registry, allocator)

    result1 = allocator.allocate("tgt-shahed-01", target_pos, target_speed, "ENEMY_UAV")
    print(f"  Allocated: {result1.allocated}")
    if result1.allocation:
        print(
            "  Effector: "
            f"{result1.allocation.effector_type.value} in "
            f"{result1.allocation.echelon.value} echelon"
        )
        print(f"  Slant range: {result1.allocation.slant_range_m:.0f}m")
        print(f"  Pk estimate: {result1.allocation.pk_estimate:.2f}")
        print(f"  Alternatives: {result1.alternatives_count}")
        print(f"  Reasoning: {result1.reasoning}")

    # Step 3: Interceptor drone misses, target moves closer
    print("\n[3] MISS — Interceptor drone failed to neutralize. Target now at 12km.")
    new_pos = (12000.0, 0.0, 1500.0)
    new_speed = 90.0

    result2 = miss_handler.report_miss(result1.allocation, new_pos, new_speed)
    print(f"  Re-allocated: {result2.allocated}")
    if result2.allocation:
        print(
            "  Fallback effector: "
            f"{result2.allocation.effector_type.value} in "
            f"{result2.allocation.echelon.value} echelon"
        )
        print(f"  New slant range: {result2.allocation.slant_range_m:.0f}m")
        print(f"  Reasoning: {result2.reasoning}")

    # Step 4: SAM engages — kill confirmed
    print("\n[4] KILL CONFIRMED — Short-range SAM destroyed the target.")
    if result2.allocation:
        miss_handler.report_kill(result2.allocation)

    # Summary
    print("\n" + "=" * 70)
    print("ENGAGEMENT SUMMARY")
    final_stats = registry.get_stats()
    print(f"  Effectors ready: {final_stats['ready']}/{final_stats['total']}")
    print(f"  Total ammo remaining: {final_stats['total_ammo']}")
    miss_stats = miss_handler.get_miss_stats()
    print(f"  Misses recorded: {miss_stats['total_misses']}")
    print(f"  Allocation log entries: {len(allocator.get_allocation_log())}")
    print("=" * 70)
    print("Demo complete. S3M air defense subsystem operational.")


if __name__ == "__main__":
    main()
