"""Saudi-oriented tactical template presets for air-defense deployment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    DefenseEchelon,
    Effector,
    EffectorCategory,
    EffectorType,
    EngagementEnvelope,
)
from services.air_defense.zone_manager import ZoneManager


@dataclass
class AirDefenseUnit:
    """Deployment result for a generated tactical unit."""

    unit_name: str
    zone_ids: list[str]
    effector_ids: list[str]


def _make_effector(
    name_en: str,
    name_ar: str,
    effector_type: EffectorType,
    category: EffectorCategory,
    echelon: DefenseEchelon,
    envelope: EngagementEnvelope,
    position: tuple[float, float, float],
) -> Effector:
    return Effector(
        name_en=name_en,
        name_ar=name_ar,
        effector_type=effector_type,
        category=category,
        echelon=echelon,
        envelope=envelope,
        position=position,
        ammunition_total=8 if category != EffectorCategory.CIWS_GUN else 240,
        ammunition_remaining=8 if category != EffectorCategory.CIWS_GUN else 240,
    )


def _build_batch(
    count: int,
    prefix_en: str,
    prefix_ar: str,
    effector_type: EffectorType,
    category: EffectorCategory,
    echelon: DefenseEchelon,
    envelope: EngagementEnvelope,
    center: tuple[float, float, float],
) -> Iterable[Effector]:
    for idx in range(1, count + 1):
        yield _make_effector(
            name_en=f"{prefix_en} {idx}",
            name_ar=f"{prefix_ar} {idx}",
            effector_type=effector_type,
            category=category,
            echelon=echelon,
            envelope=envelope,
            position=center,
        )


def create_krechet_equivalent_unit(
    registry: EffectorRegistry,
    zone_manager: ZoneManager,
    center: tuple[float, float, float],
) -> AirDefenseUnit:
    """Create a layered unit sized like a Krechet-equivalent package.

    Military context:
    This template emphasizes deep engagement capacity (extended + medium rings)
    while preserving terminal close-in guns for leakers.
    """
    zones = zone_manager.create_standard_echelons(center)
    zone_by_echelon = {zone.echelon: zone for zone in zones}

    batches = [
        # 2 + 3 = 5 extended ring systems.
        (
            2,
            "Patriot Battery",
            "بطارية باتريوت",
            EffectorType.PATRIOT_PAC3,
            EffectorCategory.SAM_LONG,
            DefenseEchelon.EXTENDED,
            EngagementEnvelope(15000, 160000, 50, 35000, pk_single_shot=0.87),
        ),
        (
            3,
            "THAAD Launcher",
            "قاذف ثاد",
            EffectorType.THAAD,
            EffectorCategory.SAM_LONG,
            DefenseEchelon.EXTENDED,
            EngagementEnvelope(30000, 200000, 1000, 40000, pk_single_shot=0.90),
        ),
        # 4 + 6 = 10 medium ring systems.
        (
            4,
            "BUK-FS Battery",
            "بطارية بوك",
            EffectorType.BUK_FS,
            EffectorCategory.SAM_MEDIUM,
            DefenseEchelon.MEDIUM,
            EngagementEnvelope(3000, 45000, 15, 25000, pk_single_shot=0.81),
        ),
        (
            6,
            "NASAMS Battery",
            "بطارية ناسامز",
            EffectorType.NASAMS,
            EffectorCategory.SAM_MEDIUM,
            DefenseEchelon.MEDIUM,
            EngagementEnvelope(2500, 38000, 15, 18000, pk_single_shot=0.78),
        ),
        # 5 short ring + 2 close ring systems.
        (
            5,
            "SHORAD Unit",
            "وحدة شوراد",
            EffectorType.SHORAD,
            EffectorCategory.SAM_SHORT,
            DefenseEchelon.SHORT,
            EngagementEnvelope(800, 12000, 5, 9000, pk_single_shot=0.66),
        ),
        (
            2,
            "SKYNEX CIWS",
            "سكاي نكس",
            EffectorType.SKYNEX,
            EffectorCategory.CIWS_GUN,
            DefenseEchelon.CLOSE,
            EngagementEnvelope(200, 4000, 5, 3000, pk_single_shot=0.55),
        ),
    ]

    effector_ids: list[str] = []
    for count, prefix_en, prefix_ar, eff_type, category, echelon, envelope in batches:
        zone = zone_by_echelon[echelon]
        for effector in _build_batch(
            count=count,
            prefix_en=prefix_en,
            prefix_ar=prefix_ar,
            effector_type=eff_type,
            category=category,
            echelon=echelon,
            envelope=envelope,
            center=center,
        ):
            effector.assigned_zone_id = zone.zone_id
            registry.register(effector)
            zone_manager.assign_effector_to_zone(zone.zone_id, effector.effector_id)
            effector_ids.append(effector.effector_id)

    return AirDefenseUnit(
        unit_name="krechet-equivalent",
        zone_ids=[zone.zone_id for zone in zones],
        effector_ids=effector_ids,
    )

