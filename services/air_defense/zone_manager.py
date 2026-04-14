"""Defense zone manager for layered Saudi/GCC air defense layouts.

Military context:
Zone assignment mirrors doctrinal practice where extended, medium, short,
and close echelons are coordinated to create overlapping engagement belts.
"""

from __future__ import annotations

from typing import Dict, List, Tuple
from uuid import uuid4

from services.air_defense.models import DefenseEchelon, DefenseZone


class ZoneManager:
    """Build and track tactical zones used for effector coordination."""

    def __init__(self) -> None:
        self._zones: Dict[str, DefenseZone] = {}

    def create_standard_echelons(
        self,
        center: Tuple[float, float, float],
        defended_asset_name: str,
        defended_asset_name_ar: str,
    ) -> List[DefenseZone]:
        """Create doctrinally layered radial zones around defended asset."""
        if len(center) != 3:
            raise ValueError("center must be a 3D coordinate tuple")
        if not defended_asset_name.strip() or not defended_asset_name_ar.strip():
            raise ValueError("defended asset names must be non-empty")

        # Rings are ordered from outer early-warning/intercept to inner point defense.
        ring_definitions = [
            (DefenseEchelon.EXTENDED, 25000.0, 60000.0),
            (DefenseEchelon.MEDIUM, 8000.0, 35000.0),
            (DefenseEchelon.SHORT, 2000.0, 18000.0),
            (DefenseEchelon.CLOSE, 0.0, 8000.0),
        ]
        zones: List[DefenseZone] = []
        for echelon, radius_min_m, radius_max_m in ring_definitions:
            zone = DefenseZone(
                zone_id=f"zone-{echelon.value}-{uuid4().hex[:10]}",
                echelon=echelon,
                center=center,
                radius_min_m=radius_min_m,
                radius_max_m=radius_max_m,
                defended_asset_name=defended_asset_name,
                defended_asset_name_ar=defended_asset_name_ar,
            )
            self._zones[zone.zone_id] = zone
            zones.append(zone)
        return zones

    def assign_effector_to_zone(self, zone_id: str, effector_id: str) -> None:
        """Link an effector to its tactical zone for battle management."""
        zone = self._zones.get(zone_id)
        if zone is None:
            raise ValueError(f"zone not found: {zone_id}")
        if not effector_id.strip():
            raise ValueError("effector_id must be non-empty")
        if effector_id not in zone.assigned_effector_ids:
            zone.assigned_effector_ids.append(effector_id)

    def get_zone(self, zone_id: str) -> DefenseZone | None:
        """Return one zone by ID, if present."""
        return self._zones.get(zone_id)

    def list_zones(self) -> List[DefenseZone]:
        """Return all tracked zones."""
        return list(self._zones.values())
