"""Saudi-style layered air-defense unit templates.

Military context:
Templates provide ready-to-deploy force packages that mirror operationally
relevant missile, gun, and MANPADS layering for sovereign C2 rehearsals.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

from services.air_defense.models import (
    AirDefenseUnit,
    DefenseEchelon,
    DefenseZone,
    Effector,
    EffectorCategory,
    EffectorState,
    EffectorType,
    EngagementEnvelope,
)


_ECHELON_RADIUS_BANDS: Dict[DefenseEchelon, Tuple[float, float]] = {
    DefenseEchelon.CLOSE: (0.0, 10.0),
    DefenseEchelon.SHORT: (10.0, 20.0),
    DefenseEchelon.MEDIUM: (20.0, 40.0),
}


def _effector_blueprints() -> List[Dict[str, object]]:
    return [
        {"suffix": "patriot-1", "type": EffectorType.PATRIOT_PAC3, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.MEDIUM, "name_en": "Patriot PAC-3 Battery", "name_ar": "Patriot PAC-3 Battery", "range": (20.0, 40.0), "alt": (100.0, 24000.0), "ammo": 16, "reload": 50.0},
        {"suffix": "thaad-1", "type": EffectorType.THAAD, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.MEDIUM, "name_en": "THAAD Interceptor Unit", "name_ar": "THAAD Interceptor Unit", "range": (25.0, 40.0), "alt": (1000.0, 50000.0), "ammo": 8, "reload": 120.0},
        {"suffix": "hawk-1", "type": EffectorType.HAWK_XXI, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.MEDIUM, "name_en": "HAWK XXI Battery", "name_ar": "HAWK XXI Battery", "range": (20.0, 35.0), "alt": (80.0, 18000.0), "ammo": 12, "reload": 70.0},
        {"suffix": "samp-t-1", "type": EffectorType.SAMP_T, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.MEDIUM, "name_en": "SAMP/T Equivalent Battery", "name_ar": "SAMP/T Equivalent Battery", "range": (20.0, 40.0), "alt": (100.0, 25000.0), "ammo": 12, "reload": 80.0},
        {"suffix": "sky-dragon-1", "type": EffectorType.SKY_DRAGON, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.SHORT, "name_en": "Sky Dragon Battery", "name_ar": "Sky Dragon Battery", "range": (10.0, 20.0), "alt": (60.0, 12000.0), "ammo": 12, "reload": 55.0},
        {"suffix": "nasams-1", "type": EffectorType.NASAMS_AMRAAM, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.SHORT, "name_en": "NASAMS AMRAAM Section", "name_ar": "NASAMS AMRAAM Section", "range": (10.0, 20.0), "alt": (50.0, 14000.0), "ammo": 18, "reload": 45.0},
        {"suffix": "spyder-1", "type": EffectorType.SPYDER_SR, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.SHORT, "name_en": "SPYDER SR Launcher", "name_ar": "SPYDER SR Launcher", "range": (10.0, 20.0), "alt": (30.0, 9000.0), "ammo": 8, "reload": 35.0},
        {"suffix": "shahine-1", "type": EffectorType.SHAHINE, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.SHORT, "name_en": "Shahine Missile Unit", "name_ar": "Shahine Missile Unit", "range": (10.0, 20.0), "alt": (30.0, 7000.0), "ammo": 8, "reload": 35.0},
        {"suffix": "iris-sls-1", "type": EffectorType.IRIS_T_SLS, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.SHORT, "name_en": "IRIS-T SLS Unit", "name_ar": "IRIS-T SLS Unit", "range": (10.0, 20.0), "alt": (30.0, 10000.0), "ammo": 8, "reload": 40.0},
        {"suffix": "crotal-1", "type": EffectorType.CROTAL_NG, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.CLOSE, "name_en": "Crotal NG Point Defense", "name_ar": "Crotal NG Point Defense", "range": (0.5, 10.0), "alt": (20.0, 6000.0), "ammo": 8, "reload": 25.0},
        {"suffix": "avenger-1", "type": EffectorType.AVENGER, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.CLOSE, "name_en": "Avenger SHORAD Vehicle", "name_ar": "Avenger SHORAD Vehicle", "range": (0.5, 8.0), "alt": (20.0, 4500.0), "ammo": 8, "reload": 20.0},
        {"suffix": "pantsir-1", "type": EffectorType.PANTSIR_S1, "category": EffectorCategory.MISSILE, "echelon": DefenseEchelon.CLOSE, "name_en": "Pantsir Equivalent Point Defense", "name_ar": "Pantsir Equivalent Point Defense", "range": (1.0, 10.0), "alt": (20.0, 8000.0), "ammo": 12, "reload": 25.0},
        {"suffix": "skyguard-1", "type": EffectorType.SKYGUARD_35MM, "category": EffectorCategory.GUN, "echelon": DefenseEchelon.CLOSE, "name_en": "Skyguard 35mm Battery", "name_ar": "Skyguard 35mm Battery", "range": (0.3, 6.0), "alt": (0.0, 3500.0), "ammo": 240, "reload": 6.0},
        {"suffix": "oerlikon-1", "type": EffectorType.OERLIKON_GDF005, "category": EffectorCategory.GUN, "echelon": DefenseEchelon.CLOSE, "name_en": "Oerlikon GDF-005 Battery", "name_ar": "Oerlikon GDF-005 Battery", "range": (0.3, 5.0), "alt": (0.0, 3000.0), "ammo": 220, "reload": 5.0},
        {"suffix": "zsu-1", "type": EffectorType.ZSU_23_4, "category": EffectorCategory.GUN, "echelon": DefenseEchelon.CLOSE, "name_en": "ZSU-23-4 Mobile Gun", "name_ar": "ZSU-23-4 Mobile Gun", "range": (0.2, 3.0), "alt": (0.0, 2000.0), "ammo": 200, "reload": 4.0},
        {"suffix": "mistral-1", "type": EffectorType.MISTRAL_MANPADS, "category": EffectorCategory.MANPADS, "echelon": DefenseEchelon.CLOSE, "name_en": "Mistral MANPADS Team", "name_ar": "Mistral MANPADS Team", "range": (0.5, 6.0), "alt": (10.0, 3000.0), "ammo": 6, "reload": 18.0},
        {"suffix": "stinger-1", "type": EffectorType.STINGER_MANPADS, "category": EffectorCategory.MANPADS, "echelon": DefenseEchelon.CLOSE, "name_en": "Stinger MANPADS Team", "name_ar": "Stinger MANPADS Team", "range": (0.5, 5.0), "alt": (10.0, 3500.0), "ammo": 6, "reload": 18.0},
        {"suffix": "qw18-1", "type": EffectorType.QW18_MANPADS, "category": EffectorCategory.MANPADS, "echelon": DefenseEchelon.CLOSE, "name_en": "QW-18 MANPADS Team", "name_ar": "QW-18 MANPADS Team", "range": (0.5, 5.0), "alt": (10.0, 3200.0), "ammo": 6, "reload": 16.0},
        {"suffix": "laser-1", "type": EffectorType.SHORAD_LASER, "category": EffectorCategory.DIRECTED_ENERGY, "echelon": DefenseEchelon.CLOSE, "name_en": "SHORAD Laser Cell", "name_ar": "SHORAD Laser Cell", "range": (0.2, 4.0), "alt": (0.0, 2500.0), "ammo": 100, "reload": 2.0},
        {"suffix": "ekill-1", "type": EffectorType.ELECTRONIC_KILL, "category": EffectorCategory.ELECTRONIC_WARFARE, "echelon": DefenseEchelon.SHORT, "name_en": "Electronic Kill Cell", "name_ar": "Electronic Kill Cell", "range": (1.0, 15.0), "alt": (0.0, 9000.0), "ammo": 120, "reload": 1.0},
    ]


def _layered_zones(unit_id: str, center: Tuple[float, float], name_en: str, name_ar: str) -> List[DefenseZone]:
    zones: List[DefenseZone] = []
    for echelon in (DefenseEchelon.CLOSE, DefenseEchelon.SHORT, DefenseEchelon.MEDIUM):
        min_radius, max_radius = _ECHELON_RADIUS_BANDS[echelon]
        zones.append(
            DefenseZone(
                zone_id=f"{unit_id}-{echelon.value}-zone",
                name_en=f"{name_en} {echelon.value.title()} Layer",
                name_ar=f"{name_ar} {echelon.value.title()} Layer",
                echelon=echelon,
                center=center,
                min_radius_km=min_radius,
                radius_km=max_radius,
                unit_id=unit_id,
            )
        )
    return zones


def _position_for_blueprint(
    *,
    center: Tuple[float, float],
    echelon: DefenseEchelon,
    index: int,
    total: int,
) -> Tuple[float, float, float]:
    min_radius, max_radius = _ECHELON_RADIUS_BANDS[echelon]
    radius = min_radius + (max_radius - min_radius) * 0.55
    angle_deg = (360.0 / max(1, total)) * index
    angle_rad = math.radians(angle_deg)
    x = center[0] + radius * math.cos(angle_rad)
    y = center[1] + radius * math.sin(angle_rad)
    return (x, y, 0.0)


def build_saudi_air_defense_unit(
    *,
    unit_id: str = "saudi-ad-unit-1",
    center: Tuple[float, float] = (0.0, 0.0),
    name_en: str = "Saudi Layered Air Defense Unit",
    name_ar: str = "Saudi Layered Air Defense Unit",
) -> AirDefenseUnit:
    """Build one layered Saudi-equivalent air-defense unit template."""
    zones = _layered_zones(unit_id=unit_id, center=center, name_en=name_en, name_ar=name_ar)
    zone_ids = {zone.echelon: zone.zone_id for zone in zones}
    blueprints = _effector_blueprints()
    effectors: List[Effector] = []
    for index, blueprint in enumerate(blueprints):
        echelon = blueprint["echelon"]
        envelope = EngagementEnvelope(
            min_range_km=float(blueprint["range"][0]),
            max_range_km=float(blueprint["range"][1]),
            min_altitude_m=float(blueprint["alt"][0]),
            max_altitude_m=float(blueprint["alt"][1]),
        )
        effectors.append(
            Effector(
                effector_id=f"{unit_id}-{blueprint['suffix']}",
                name_en=str(blueprint["name_en"]),
                name_ar=str(blueprint["name_ar"]),
                effector_type=blueprint["type"],
                category=blueprint["category"],
                echelon=echelon,
                envelope=envelope,
                state=EffectorState(
                    readiness=1.0,
                    ammunition_current=int(blueprint["ammo"]),
                    ammunition_capacity=int(blueprint["ammo"]),
                    reload_time_seconds=float(blueprint["reload"]),
                ),
                zone_id=zone_ids[echelon],
                position=_position_for_blueprint(center=center, echelon=echelon, index=index, total=len(blueprints)),
                priority=50 + index,
            )
        )
    return AirDefenseUnit(
        unit_id=unit_id,
        name_en=name_en,
        name_ar=name_ar,
        effectors=effectors,
        zones=zones,
        metadata={"template": "saudi_layered_air_defense", "effector_count": len(effectors)},
    )


def build_saudi_regional_templates() -> Sequence[AirDefenseUnit]:
    """Build multiple pre-configured Saudi regional defense templates."""
    return [
        build_saudi_air_defense_unit(
            unit_id="saudi-riyadh-core",
            center=(0.0, 0.0),
            name_en="Riyadh Core Defense Group",
            name_ar="Riyadh Core Defense Group",
        ),
        build_saudi_air_defense_unit(
            unit_id="saudi-eastern-energy-shield",
            center=(120.0, -15.0),
            name_en="Eastern Energy Shield Group",
            name_ar="Eastern Energy Shield Group",
        ),
        build_saudi_air_defense_unit(
            unit_id="saudi-red-sea-front",
            center=(-90.0, 40.0),
            name_en="Red Sea Front Defense Group",
            name_ar="Red Sea Front Defense Group",
        ),
    ]
