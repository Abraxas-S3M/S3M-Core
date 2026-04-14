"""Unit tests for interceptor kill-chain integration hooks.

Military context:
These tests validate additive service handoffs required for Krechet-equivalent
engagement flow: allocator launches interceptor guidance, and radar fusion
feeds confirmed track updates back into interceptor midcourse guidance.
"""

from __future__ import annotations

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import Effector, EffectorCategory, EffectorEnvelope
from services.air_defense.target_allocator import TargetAllocator
from services.radar.models import RadarConfig
from services.radar.radar_manager import RadarManager


def _effector(
    effector_id: str,
    category: EffectorCategory,
    *,
    readiness: float = 1.0,
    max_range_m: float = 10_000.0,
) -> Effector:
    return Effector(
        effector_id=effector_id,
        name_en=effector_id.upper(),
        effector_type=category.value,
        category=category,
        echelon="battery-alpha",
        position=(0.0, 0.0, 0.0),
        envelope=EffectorEnvelope(
            min_range_m=0.0,
            max_range_m=max_range_m,
            pk_single_shot=0.8,
        ),
        readiness_score=readiness,
        assigned_zone_id="zone-a",
    )


def test_allocator_starts_interceptor_guidance_for_interceptor_drone() -> None:
    class FakeInterceptorManager:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def assign_target(self, interceptor_id: str, target_id: str) -> bool:
            self.calls.append(("assign_target", interceptor_id, target_id))
            return True

        def launch(self, interceptor_id: str) -> bool:
            self.calls.append(("launch", interceptor_id, ""))
            return True

    registry = EffectorRegistry()
    registry.register(_effector("int-1", EffectorCategory.INTERCEPTOR_DRONE))
    fake_manager = FakeInterceptorManager()
    allocator = TargetAllocator(registry=registry, interceptor_manager=fake_manager)

    result = allocator.allocate(
        target_id="trk-1",
        target_position=(500.0, 0.0, 100.0),
        target_speed_mps=120.0,
        target_classification="ENEMY_UAV",
    )

    assert result.allocated is True
    assert fake_manager.calls == [
        ("assign_target", "int-1", "trk-1"),
        ("launch", "int-1", ""),
    ]


def test_radar_fusion_guides_active_interception_on_confirmed_track() -> None:
    class FakeInterceptorGuidanceManager:
        def __init__(self) -> None:
            self.guide_calls: list[dict[str, object]] = []

        def get_active_interceptions(self) -> list[dict[str, str]]:
            return [{"interceptor_id": "int-1", "target_id": "trk-1"}]

        def guide(
            self,
            interceptor_id: str,
            interceptor_pos: tuple[float, float, float],
            interceptor_vel: tuple[float, float, float],
            target_pos: tuple[float, float, float],
            target_vel: tuple[float, float, float],
        ) -> None:
            self.guide_calls.append(
                {
                    "interceptor_id": interceptor_id,
                    "interceptor_pos": interceptor_pos,
                    "interceptor_vel": interceptor_vel,
                    "target_pos": target_pos,
                    "target_vel": target_vel,
                }
            )

    guidance_manager = FakeInterceptorGuidanceManager()
    radar_manager = RadarManager(interceptor_manager=guidance_manager)
    radar = radar_manager.register_radar(RadarConfig())

    radar_manager.ingest_scan(
        radar.radar_id,
        {
            "plots": [
                {
                    "position": [100.0, 0.0, 50.0],
                    "correlated_track_id": "trk-1",
                    "rcs_classification": "small_uav",
                }
            ]
        },
    )
    radar_manager.ingest_scan(
        radar.radar_id,
        {
            "plots": [
                {
                    "position": [90.0, 0.0, 45.0],
                    "correlated_track_id": "trk-1",
                    "rcs_classification": "small_uav",
                }
            ]
        },
    )

    radar_manager.process_fused_tracks()

    assert len(guidance_manager.guide_calls) == 1
    call = guidance_manager.guide_calls[0]
    assert call["interceptor_id"] == "int-1"
    assert call["target_pos"] == (90.0, 0.0, 45.0)
    assert call["interceptor_pos"] == (0.0, 0.0, 0.0)
