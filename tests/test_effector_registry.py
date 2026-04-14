"""Unit tests for tactical air-defense effector registry."""

from __future__ import annotations

import pytest

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    DefenseEchelon,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
)


def _mk_effector(effector_id: str, **overrides: object) -> Effector:
    payload = {
        "effector_id": effector_id,
        "category": EffectorCategory.MISSILE,
        "echelon": DefenseEchelon.OPERATIONAL,
        "effector_type": EffectorType.SAM,
        "state": EffectorState.READY,
        "assigned_zone_id": "zone-alpha",
        "position": (0.0, 0.0, 0.0),
        "engagement_range_m": 50000.0,
        "min_range_m": 100.0,
        "max_target_speed_mps": 1500.0,
        "ammunition_total": 10,
        "ammunition_remaining": 10,
    }
    payload.update(overrides)
    return Effector(**payload)


def test_registry_register_get_list_and_count() -> None:
    registry = EffectorRegistry()
    effector = _mk_effector("eff-1")

    registry.register(effector)

    assert registry.get("eff-1") is effector
    assert registry.count() == 1
    assert registry.list_all() == [effector]


def test_register_rejects_invalid_object() -> None:
    registry = EffectorRegistry()
    with pytest.raises(ValueError, match="Effector instance"):
        registry.register("not-an-effector")  # type: ignore[arg-type]


def test_query_filters_by_type_zone_state_and_availability() -> None:
    registry = EffectorRegistry()
    registry.register(_mk_effector("a", assigned_zone_id="zone-a"))
    registry.register(
        _mk_effector(
            "b",
            state=EffectorState.RELOADING,
            assigned_zone_id="zone-b",
            ammunition_remaining=0,
        )
    )
    registry.register(
        _mk_effector(
            "c",
            category=EffectorCategory.GUN,
            echelon=DefenseEchelon.POINT,
            effector_type=EffectorType.CIWS,
            assigned_zone_id="zone-a",
            ammunition_total=2,
            ammunition_remaining=2,
        )
    )

    assert {e.effector_id for e in registry.query(category=EffectorCategory.MISSILE)} == {
        "a",
        "b",
    }
    assert {e.effector_id for e in registry.query(zone_id="zone-a")} == {"a", "c"}
    assert {e.effector_id for e in registry.query(state=EffectorState.RELOADING)} == {
        "b"
    }
    assert {e.effector_id for e in registry.query(available_only=True)} == {"a", "c"}


def test_get_available_for_target_sorts_by_readiness() -> None:
    registry = EffectorRegistry()
    low_ready = _mk_effector(
        "low",
        ammunition_total=10,
        ammunition_remaining=4,
        position=(0.0, 0.0, 0.0),
    )
    high_ready = _mk_effector(
        "high",
        ammunition_total=10,
        ammunition_remaining=9,
        position=(0.0, 0.0, 0.0),
    )
    too_slow = _mk_effector(
        "slow",
        max_target_speed_mps=200.0,
        position=(0.0, 0.0, 0.0),
    )
    registry.register(low_ready)
    registry.register(high_ready)
    registry.register(too_slow)

    matches = registry.get_available_for_target(
        target_position=(1000.0, 0.0, 0.0),
        target_speed_mps=300.0,
    )

    assert [e.effector_id for e in matches] == ["high", "low"]


def test_state_update_and_resupply_transition_to_ready() -> None:
    registry = EffectorRegistry()
    effector = _mk_effector(
        "reload-1",
        state=EffectorState.RELOADING,
        ammunition_total=6,
        ammunition_remaining=0,
    )
    registry.register(effector)

    assert registry.update_state("reload-1", EffectorState.RELOADING) is True
    assert registry.resupply("reload-1") is True
    assert effector.ammunition_remaining == 6
    assert effector.state == EffectorState.READY
    assert registry.resupply("reload-1", rounds=3) is True
    assert effector.ammunition_remaining == 3
    assert registry.update_state("missing", EffectorState.READY) is False
    assert registry.resupply("missing", rounds=1) is False


def test_stats_and_remove_track_inventory_state() -> None:
    registry = EffectorRegistry()
    registry.register(_mk_effector("ready", ammunition_remaining=5, ammunition_total=5))
    registry.register(
        _mk_effector(
            "engaging",
            state=EffectorState.ENGAGING,
            ammunition_remaining=2,
            ammunition_total=8,
        )
    )
    registry.register(
        _mk_effector(
            "offline",
            state=EffectorState.OFFLINE,
            ammunition_remaining=0,
            ammunition_total=4,
        )
    )

    stats = registry.get_stats()

    assert stats["total"] == 3
    assert stats["ready"] == 1
    assert stats["engaging"] == 1
    assert stats["offline"] == 1
    assert stats["available"] == 1
    assert stats["total_ammo"] == 7
    assert registry.remove("offline") is True
    assert registry.remove("offline") is False
