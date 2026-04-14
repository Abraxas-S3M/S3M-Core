"""Layered defended-airspace zone manager.

Military context:
Encodes concentric tactical defense rings so threats are engaged at standoff
distance first, preserving inner-layer ammunition for leakage and saturation.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from services.air_defense.models import AirDefenseZone, DefenseEchelon


ECHELON_PRIORITY = [
    DefenseEchelon.EXTENDED,
    DefenseEchelon.MEDIUM,
    DefenseEchelon.SHORT,
    DefenseEchelon.CLOSE,
]
_ECHELON_INDEX = {echelon: idx for idx, echelon in enumerate(ECHELON_PRIORITY)}


class ZoneManager:
    """Store and query layered zones for tactical target location checks."""

    def __init__(self, zones: Optional[List[AirDefenseZone]] = None) -> None:
        self._zones: List[AirDefenseZone] = []
        for zone in zones or []:
            self.add_zone(zone)

    def add_zone(self, zone: AirDefenseZone) -> None:
        existing = {item.zone_id: item for item in self._zones}
        existing[zone.zone_id] = zone
        self._zones = sorted(
            existing.values(),
            key=lambda item: _ECHELON_INDEX.get(item.echelon, len(ECHELON_PRIORITY)),
        )

    def get_zone(self, zone_id: str) -> Optional[AirDefenseZone]:
        for zone in self._zones:
            if zone.zone_id == zone_id:
                return zone
        return None

    def list_zones(self) -> List[AirDefenseZone]:
        return list(self._zones)

    def find_zones_for_target(
        self, target_position: Tuple[float, float, float]
    ) -> List[AirDefenseZone]:
        """Return all zones containing target, ordered by doctrine priority."""
        containing = [
            zone for zone in self._zones if zone.contains_target(target_position)
        ]
        return sorted(
            containing,
            key=lambda zone: _ECHELON_INDEX.get(zone.echelon, len(ECHELON_PRIORITY)),
        )
