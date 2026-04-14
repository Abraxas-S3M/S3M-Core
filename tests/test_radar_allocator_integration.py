"""Tests for radar-to-air-defense allocator integration.

Military context:
Confirmed hostile air tracks should trigger a single deterministic
allocation request into layered air defense effectors.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.radar.models import RadarConfig, TrackState
from services.radar.radar_manager import RadarManager


class _StubAllocator:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def allocate(
        self,
        target_id: str,
        target_position: tuple[float, float, float],
        target_speed_mps: float,
        target_classification: str,
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "target_id": target_id,
                "target_position": target_position,
                "target_speed_mps": target_speed_mps,
                "target_classification": target_classification,
            }
        )
        return {"allocated": True}


def test_confirmed_enemy_uav_track_triggers_single_allocation() -> None:
    allocator = _StubAllocator()
    manager = RadarManager(air_defense_allocator=allocator)
    radar = manager.register_radar(config=RadarConfig(name_en="stub"))

    manager.ingest_scan(
        radar.radar_id,
        {"plots": [{"position": [100.0, 200.0, 50.0], "rcs_classification": "small_uav", "track_id": "trk-alloc"}]},
    )
    first_pass = manager.process_fused_tracks()
    assert first_pass[0].state is TrackState.TENTATIVE
    assert allocator.calls == []

    manager.ingest_scan(
        radar.radar_id,
        {"plots": [{"position": [110.0, 205.0, 52.0], "rcs_classification": "small_uav", "track_id": "trk-alloc"}]},
    )
    second_pass = manager.process_fused_tracks()
    assert second_pass[0].state is TrackState.CONFIRMED
    assert len(allocator.calls) == 1
    assert allocator.calls[0]["target_id"] == "trk-alloc"
    assert allocator.calls[0]["target_classification"] == "ENEMY_UAV"

    # Re-processing the same confirmed track should not issue duplicate fires.
    manager.process_fused_tracks()
    assert len(allocator.calls) == 1


def test_confirmed_enemy_helicopter_classification_is_allocated() -> None:
    allocator = _StubAllocator()
    manager = RadarManager(air_defense_allocator=allocator)
    radar = manager.register_radar(config=RadarConfig(name_en="stub"))

    manager.ingest_scan(
        radar.radar_id,
        {"plots": [{"position": [300.0, 100.0, 120.0], "track_id": "trk-helo", "classification": "ENEMY_HELICOPTER"}]},
    )
    manager.process_fused_tracks()
    manager.ingest_scan(
        radar.radar_id,
        {"plots": [{"position": [320.0, 105.0, 120.0], "track_id": "trk-helo", "classification": "ENEMY_HELICOPTER"}]},
    )
    manager.process_fused_tracks()

    assert len(allocator.calls) == 1
    assert allocator.calls[0]["target_classification"] == "ENEMY_HELICOPTER"
