"""Pre-built Saudi air defense unit templates.

Military context:
Provides ready-to-use effector configurations modeling realistic
Saudi/GCC air defense deployments. Effector performance envelopes are
based on publicly available specifications of the referenced systems.
"""

from __future__ import annotations

from typing import List, Tuple

from services.air_defense.effector_registry import EffectorRegistry
from services.air_defense.models import (
    AirDefenseUnit,
    DefenseEchelon,
    Effector,
    EffectorCategory,
    EffectorType,
    EngagementEnvelope,
)
from services.air_defense.zone_manager import ZoneManager


def create_krechet_equivalent_unit(
    registry: EffectorRegistry,
    zone_manager: ZoneManager,
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    defended_asset: str = "Critical Infrastructure",
    defended_asset_ar: str = "البنية التحتية الحيوية",
) -> AirDefenseUnit:
    """Create a full Krechet-equivalent air defense unit with all echelons populated.

    Returns an AirDefenseUnit with:
    - 2 medium-range SAM launchers (BUK-FS equivalent)
    - 3 short-range SAM launchers (Itel SNC / Dash-Stash equivalent)
    - 4 close-range gun/missile systems (Skynex/Skyranger/Typhoon equivalent)
    - 6 MANPADS teams
    - 5 interceptor drone stations (Titan equivalent)
    - 2 EW jammers
    """
    # Build a layered zone stack to mirror tactical rings around the asset.
    zones = zone_manager.create_standard_echelons(
        center=center,
        defended_asset_name=defended_asset,
        defended_asset_name_ar=defended_asset_ar,
    )
    zone_map = {zone.echelon: zone for zone in zones}

    effectors: List[Effector] = []

    # --- Medium-range SAM (20-40km) ---
    for i in range(2):
        eff = Effector(
            name_en=f"BUK-FS Launcher #{i+1}",
            name_ar=f"منصة بوك-أف أس #{i+1}",
            effector_type=EffectorType.BUK_FS,
            category=EffectorCategory.SAM_MEDIUM,
            echelon=DefenseEchelon.MEDIUM,
            envelope=EngagementEnvelope(
                min_range_m=3000,
                max_range_m=40000,
                min_altitude_m=15,
                max_altitude_m=25000,
                max_target_speed_mps=830,
                reaction_time_s=12,
                engagement_time_s=25,
                simultaneous_targets=2,
                pk_single_shot=0.80,
            ),
            position=(center[0] + 200 * (i - 0.5), center[1] - 500, center[2]),
            ammunition_total=4,
            ammunition_remaining=4,
            reload_time_s=300,
            assigned_zone_id=zone_map[DefenseEchelon.MEDIUM].zone_id,
        )
        effectors.append(registry.register(eff))
        zone_manager.assign_effector_to_zone(zone_map[DefenseEchelon.MEDIUM].zone_id, eff.effector_id)

    # --- Short-range SAM (5-20km) ---
    short_configs = [
        ("Itel SNC", "إيتل أس أن سي", EffectorType.ITEL_SNC),
        ("Dash/Stash V2X", "داش/ستاش", EffectorType.DASH_STASH_V2X),
        ("FrankenSAM", "فرانكنسام", EffectorType.FRANKEN_SAM),
    ]
    for i, (name_en, name_ar, etype) in enumerate(short_configs):
        eff = Effector(
            name_en=f"{name_en} #{i+1}",
            name_ar=f"{name_ar} #{i+1}",
            effector_type=etype,
            category=EffectorCategory.SAM_SHORT,
            echelon=DefenseEchelon.SHORT,
            envelope=EngagementEnvelope(
                min_range_m=500,
                max_range_m=15000,
                min_altitude_m=10,
                max_altitude_m=10000,
                max_target_speed_mps=500,
                reaction_time_s=8,
                engagement_time_s=15,
                simultaneous_targets=1,
                pk_single_shot=0.70,
            ),
            position=(center[0] + 400 * (i - 1), center[1] - 200, center[2]),
            ammunition_total=8,
            ammunition_remaining=8,
            reload_time_s=120,
            assigned_zone_id=zone_map[DefenseEchelon.SHORT].zone_id,
        )
        effectors.append(registry.register(eff))
        zone_manager.assign_effector_to_zone(zone_map[DefenseEchelon.SHORT].zone_id, eff.effector_id)

    # --- Close-range gun/missile systems (0.5-10km) ---
    close_configs = [
        ("Skynex", "سكاينكس", EffectorType.SKYNEX),
        ("Skyranger", "سكايرينجر", EffectorType.SKYRANGER),
        ("RapidRanger", "رابيد رينجر", EffectorType.RAPID_RANGER),
        ("Typhoon KDA", "تايفون كي دي أيه", EffectorType.TYPHOON_KDA),
    ]
    for i, (name_en, name_ar, etype) in enumerate(close_configs):
        eff = Effector(
            name_en=f"{name_en} #{i+1}",
            name_ar=f"{name_ar} #{i+1}",
            effector_type=etype,
            category=EffectorCategory.CIWS_GUN,
            echelon=DefenseEchelon.CLOSE,
            envelope=EngagementEnvelope(
                min_range_m=200,
                max_range_m=8000,
                min_altitude_m=5,
                max_altitude_m=4000,
                max_target_speed_mps=400,
                reaction_time_s=3,
                engagement_time_s=5,
                simultaneous_targets=1,
                pk_single_shot=0.55,
            ),
            position=(center[0] + 300 * (i - 1.5), center[1] + 100, center[2]),
            ammunition_total=200,
            ammunition_remaining=200,
            reload_time_s=60,
            assigned_zone_id=zone_map[DefenseEchelon.CLOSE].zone_id,
        )
        effectors.append(registry.register(eff))
        zone_manager.assign_effector_to_zone(zone_map[DefenseEchelon.CLOSE].zone_id, eff.effector_id)

    # --- MANPADS teams ---
    for i in range(6):
        eff = Effector(
            name_en=f"MANPADS Team #{i+1}",
            name_ar=f"فريق صواريخ محمولة #{i+1}",
            effector_type=EffectorType.MANPADS_GENERIC,
            category=EffectorCategory.MANPADS,
            echelon=DefenseEchelon.CLOSE,
            envelope=EngagementEnvelope(
                min_range_m=300,
                max_range_m=6000,
                min_altitude_m=10,
                max_altitude_m=3500,
                max_target_speed_mps=360,
                reaction_time_s=6,
                engagement_time_s=8,
                simultaneous_targets=1,
                pk_single_shot=0.50,
            ),
            position=(center[0] + 250 * (i - 2.5), center[1] + 300, center[2]),
            ammunition_total=4,
            ammunition_remaining=4,
            reload_time_s=20,
            assigned_zone_id=zone_map[DefenseEchelon.CLOSE].zone_id,
        )
        effectors.append(registry.register(eff))
        zone_manager.assign_effector_to_zone(zone_map[DefenseEchelon.CLOSE].zone_id, eff.effector_id)

    # --- Interceptor drone stations (Titan equivalent) ---
    for i in range(5):
        eff = Effector(
            name_en=f"Titan Interceptor Station #{i+1}",
            name_ar=f"محطة اعتراض تيتان #{i+1}",
            effector_type=EffectorType.INTERCEPTOR_TITAN,
            category=EffectorCategory.INTERCEPTOR_DRONE,
            echelon=DefenseEchelon.EXTENDED,
            envelope=EngagementEnvelope(
                min_range_m=1000,
                max_range_m=40000,
                min_altitude_m=20,
                max_altitude_m=12000,
                max_target_speed_mps=250,
                reaction_time_s=15,
                engagement_time_s=120,
                simultaneous_targets=1,
                pk_single_shot=0.65,
            ),
            position=(center[0] + 400 * (i - 2), center[1] - 800, center[2]),
            ammunition_total=3,
            ammunition_remaining=3,
            reload_time_s=600,
            assigned_zone_id=zone_map[DefenseEchelon.EXTENDED].zone_id,
        )
        effectors.append(registry.register(eff))
        zone_manager.assign_effector_to_zone(zone_map[DefenseEchelon.EXTENDED].zone_id, eff.effector_id)

    # --- EW jammers ---
    for i in range(2):
        eff = Effector(
            name_en=f"EW Jammer #{i+1}",
            name_ar=f"جهاز تشويش إلكتروني #{i+1}",
            effector_type=EffectorType.EW_JAMMER,
            category=EffectorCategory.ELECTRONIC_WARFARE,
            echelon=DefenseEchelon.SHORT,
            envelope=EngagementEnvelope(
                min_range_m=100,
                max_range_m=15000,
                min_altitude_m=0,
                max_altitude_m=8000,
                max_target_speed_mps=600,
                reaction_time_s=2,
                engagement_time_s=0,
                simultaneous_targets=10,
                pk_single_shot=0.30,
            ),
            position=(center[0] + 600 * (i - 0.5), center[1], center[2]),
            ammunition_total=9999,
            ammunition_remaining=9999,
            reload_time_s=0,
            assigned_zone_id=zone_map[DefenseEchelon.SHORT].zone_id,
        )
        effectors.append(registry.register(eff))
        zone_manager.assign_effector_to_zone(zone_map[DefenseEchelon.SHORT].zone_id, eff.effector_id)

    unit = AirDefenseUnit(
        name_en=f"S3M Air Defense Unit - {defended_asset}",
        name_ar=f"وحدة دفاع جوي S3M - {defended_asset_ar}",
        defended_asset=defended_asset,
        position=center,
        effector_ids=[eff.effector_id for eff in effectors],
        zone_ids=[zone.zone_id for zone in zones],
    )
    return unit
