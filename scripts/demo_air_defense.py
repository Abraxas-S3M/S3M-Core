"""Demo for air-defense allocate -> engage -> miss -> reallocate cycle.

Military context:
Demonstrates doctrinal outer-layer engagement and immediate fallback to a
secondary channel when first-shot intercept fails.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.miss_handler import MissHandler
from services.air_defense.saudi_templates import build_saudi_air_defense_unit
from services.air_defense.target_allocator import TargetAllocator
from services.air_defense.zone_manager import DefenseZoneManager


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def main() -> None:
    registry = EffectorRegistry()
    zone_manager = DefenseZoneManager()
    allocator = TargetAllocator(registry=registry, zone_manager=zone_manager)
    miss_handler = MissHandler(allocator=allocator, registry=registry)

    unit = build_saudi_air_defense_unit(unit_id="demo-saudi-unit", center=(0.0, 0.0))
    for zone in unit.zones:
        zone_manager.register_zone(zone, replace_existing=True)
    for effector in unit.effectors:
        registry.register_effector(effector, replace_existing=True)

    target_id = "track-uav-001"
    target_position = (14.0, 2.0, 1400.0)
    target_type = "enemy_uav"

    print("== Initial allocation ==")
    initial = allocator.allocate_target(
        target_id=target_id,
        target_position=target_position,
        target_type=target_type,
        reserve_queue=True,
    )
    print(json.dumps(_serialize(initial), indent=2))
    if initial.selected_allocation is None:
        print("No allocation available. Demo cannot continue.")
        return

    selected_effector_id = initial.selected_allocation.assigned_effector_id
    registry.consume_ammunition(selected_effector_id, rounds=1)
    registry.record_shot(selected_effector_id, timestamp=time.time())

    print("\n== Miss assessment and fallback allocation ==")
    reallocation = miss_handler.handle_miss(
        target_id=target_id,
        target_position=target_position,
        target_type=target_type,
        previous_allocation=initial.selected_allocation,
        miss_reason="drone_miss",
    )
    print(json.dumps(_serialize(reallocation), indent=2))

    if reallocation.selected_allocation is not None:
        fallback_effector_id = reallocation.selected_allocation.assigned_effector_id
        print(f"\nFallback assigned to: {fallback_effector_id}")
    else:
        print("\nNo fallback effector available.")


if __name__ == "__main__":
    main()
