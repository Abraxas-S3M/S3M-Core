"""Unit tests for the air-defense engagement demo script."""

from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace


def _install_air_defense_stubs(monkeypatch) -> None:
    """Install tactical air-defense service stubs for deterministic demo testing."""

    services_pkg = sys.modules.get("services")
    if services_pkg is None:
        services_pkg = types.ModuleType("services")
        services_pkg.__path__ = []
        monkeypatch.setitem(sys.modules, "services", services_pkg)

    air_defense_pkg = types.ModuleType("services.air_defense")
    air_defense_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "services.air_defense", air_defense_pkg)

    class FakeEffectorRegistry:
        def __init__(self) -> None:
            self._stats = {"total": 12, "ready": 12, "total_ammo": 48}

        def get_stats(self) -> dict[str, int]:
            return dict(self._stats)

    class FakeZoneManager:
        def get_coverage_report(self) -> dict[str, dict[str, float]]:
            return {
                "EXTENDED": {"total_effectors": 4, "outer_radius_m": 40000.0},
                "MID": {"total_effectors": 4, "outer_radius_m": 20000.0},
                "SHORT": {"total_effectors": 4, "outer_radius_m": 10000.0},
            }

    class FakeTargetAllocator:
        def __init__(self, registry, zone_mgr) -> None:
            self.registry = registry
            self.zone_mgr = zone_mgr
            self._log: list[str] = []

        def allocate(self, target_id: str, target_pos, target_speed: float, target_type: str):
            _ = (target_pos, target_speed, target_type)
            self._log.append(target_id)
            allocation = SimpleNamespace(
                effector_type=SimpleNamespace(value="INTERCEPTOR_DRONE"),
                echelon=SimpleNamespace(value="EXTENDED"),
                slant_range_m=35057.0,
                pk_estimate=0.61,
            )
            return SimpleNamespace(
                allocated=True,
                allocation=allocation,
                alternatives_count=2,
                reasoning="Extended echelon selected to intercept at maximum depth.",
            )

        def get_allocation_log(self) -> list[str]:
            return list(self._log)

    class FakeMissHandler:
        def __init__(self, registry, allocator) -> None:
            self.registry = registry
            self.allocator = allocator
            self._misses = 0
            self.kills: list[object] = []

        def report_miss(self, allocation, new_pos, new_speed: float):
            _ = (allocation, new_pos, new_speed)
            self._misses += 1
            self.allocator._log.append("fallback-alloc")
            fallback = SimpleNamespace(
                effector_type=SimpleNamespace(value="SHORT_RANGE_SAM"),
                echelon=SimpleNamespace(value="SHORT"),
                slant_range_m=12093.0,
                pk_estimate=0.88,
            )
            return SimpleNamespace(
                allocated=True,
                allocation=fallback,
                reasoning="Escalated to short-range SAM after interceptor miss.",
            )

        def report_kill(self, allocation) -> None:
            self.kills.append(allocation)

        def get_miss_stats(self) -> dict[str, int]:
            return {"total_misses": self._misses}

    def fake_create_krechet_equivalent_unit(
        registry,
        zone_mgr,
        center,
        defended_asset: str,
        defended_asset_ar: str,
    ):
        _ = (registry, zone_mgr, center, defended_asset, defended_asset_ar)
        return SimpleNamespace(
            name_en="Krechet-Equivalent Saudi Unit",
            zone_ids=["EXTENDED", "MID", "SHORT"],
        )

    effector_registry_mod = types.ModuleType("services.air_defense.effector_registry")
    effector_registry_mod.EffectorRegistry = FakeEffectorRegistry
    monkeypatch.setitem(sys.modules, "services.air_defense.effector_registry", effector_registry_mod)

    zone_manager_mod = types.ModuleType("services.air_defense.zone_manager")
    zone_manager_mod.ZoneManager = FakeZoneManager
    monkeypatch.setitem(sys.modules, "services.air_defense.zone_manager", zone_manager_mod)

    allocator_mod = types.ModuleType("services.air_defense.target_allocator")
    allocator_mod.TargetAllocator = FakeTargetAllocator
    monkeypatch.setitem(sys.modules, "services.air_defense.target_allocator", allocator_mod)

    miss_handler_mod = types.ModuleType("services.air_defense.miss_handler")
    miss_handler_mod.MissHandler = FakeMissHandler
    monkeypatch.setitem(sys.modules, "services.air_defense.miss_handler", miss_handler_mod)

    templates_mod = types.ModuleType("services.air_defense.saudi_templates")
    templates_mod.create_krechet_equivalent_unit = fake_create_krechet_equivalent_unit
    monkeypatch.setitem(sys.modules, "services.air_defense.saudi_templates", templates_mod)


def test_air_defense_demo_runs_full_engagement_cycle(monkeypatch, capsys) -> None:
    _install_air_defense_stubs(monkeypatch)
    monkeypatch.delitem(sys.modules, "scripts.demo_air_defense", raising=False)

    demo_module = importlib.import_module("scripts.demo_air_defense")
    demo_module.main()

    output = capsys.readouterr().out
    assert "S3M AIR DEFENSE DEMO" in output
    assert "THREAT DETECTED" in output
    assert "MISS — Interceptor drone failed to neutralize" in output
    assert "KILL CONFIRMED — Short-range SAM destroyed the target." in output
    assert "Misses recorded: 1" in output
    assert "Allocation log entries: 2" in output
