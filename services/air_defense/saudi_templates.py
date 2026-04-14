"""Template builders for Saudi-aligned layered air-defense unit structures.

Military context:
Template generation provides a deterministic starting ORBAT for rapid setup of
multi-echelon defensive coverage around critical national infrastructure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import DefenseEchelon, DefenseZone, Effector, EffectorCategory
from services.air_defense.zone_manager import ZoneManager


@dataclass
class KrechetEquivalentUnit:
    """Summary of generated unit structure and registered component IDs."""

    unit_id: str
    name_en: str
    name_ar: str
    effector_ids: list[str]
    zone_ids: list[str]


def _new_effector_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _new_zone_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def create_krechet_equivalent_unit(
    registry: EffectorRegistry,
    zone_manager: ZoneManager,
    center: Tuple[float, float, float],
    defended_asset: str,
    defended_asset_ar: str,
) -> KrechetEquivalentUnit:
    """Create a three-echelon unit and register its effectors/zones."""
    cx, cy, cz = center
    unit_id = f"krechet-eq-{uuid.uuid4().hex[:8]}"
    effector_ids: list[str] = []
    zone_ids: list[str] = []

    short_effector = Effector(
        effector_id=_new_effector_id("ad-sr"),
        name="Short-Range Interceptor Battery",
        category=EffectorCategory.MISSILE,
        echelon=DefenseEchelon.SHORT_RANGE,
        position=(cx + 200.0, cy, cz),
        max_range_m=9_000.0,
        ammunition_capacity=8,
        ammunition_remaining=8,
    )
    medium_effector = Effector(
        effector_id=_new_effector_id("ad-mr"),
        name="Medium-Range Interceptor Battery",
        category=EffectorCategory.MISSILE,
        echelon=DefenseEchelon.MEDIUM_RANGE,
        position=(cx - 400.0, cy + 250.0, cz),
        max_range_m=35_000.0,
        ammunition_capacity=12,
        ammunition_remaining=12,
    )
    long_effector = Effector(
        effector_id=_new_effector_id("ad-lr"),
        name="Long-Range Interceptor Battery",
        category=EffectorCategory.MISSILE,
        echelon=DefenseEchelon.LONG_RANGE,
        position=(cx, cy - 500.0, cz),
        max_range_m=90_000.0,
        ammunition_capacity=16,
        ammunition_remaining=16,
    )

    for effector in (short_effector, medium_effector, long_effector):
        registry.register(effector)
        effector_ids.append(effector.effector_id)

    short_zone = DefenseZone(
        zone_id=_new_zone_id("zone-sr"),
        name="Inner Defensive Ring",
        echelon=DefenseEchelon.SHORT_RANGE,
        center=center,
        radius_m=12_000.0,
        defended_asset=defended_asset,
        defended_asset_ar=defended_asset_ar,
    )
    medium_zone = DefenseZone(
        zone_id=_new_zone_id("zone-mr"),
        name="Middle Defensive Ring",
        echelon=DefenseEchelon.MEDIUM_RANGE,
        center=center,
        radius_m=45_000.0,
        defended_asset=defended_asset,
        defended_asset_ar=defended_asset_ar,
    )
    long_zone = DefenseZone(
        zone_id=_new_zone_id("zone-lr"),
        name="Outer Defensive Ring",
        echelon=DefenseEchelon.LONG_RANGE,
        center=center,
        radius_m=120_000.0,
        defended_asset=defended_asset,
        defended_asset_ar=defended_asset_ar,
    )

    for zone in (short_zone, medium_zone, long_zone):
        zone_manager.register_zone(zone)
        zone_ids.append(zone.zone_id)

    return KrechetEquivalentUnit(
        unit_id=unit_id,
        name_en="Krechet-Equivalent Layered Air Defense Unit",
        name_ar="وحدة دفاع جوي طبقية مكافئة لكريشت",
        effector_ids=effector_ids,
        zone_ids=zone_ids,
    )

