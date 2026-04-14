"""Defense zone management for layered air-defense coverage envelopes.

Military context:
Zones represent tactical responsibility rings around defended assets and are
used to prioritize which defensive echelon should engage inbound threats.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Optional, Tuple

from services.air_defense.models import DefenseEchelon, DefenseZone


class ZoneManager:
    """In-memory zone manager for edge-deployed command-and-control nodes."""

    def __init__(self) -> None:
        self._zones: Dict[str, DefenseZone] = {}

    def register_zone(self, zone: DefenseZone) -> None:
        """Register or update one defense zone."""
        self._zones[zone.zone_id] = zone

    def list_zones(self, echelon: Optional[DefenseEchelon] = None) -> List[DefenseZone]:
        """Return all zones or only those assigned to one echelon."""
        zones = list(self._zones.values())
        if echelon is None:
            return zones
        return [zone for zone in zones if zone.echelon == echelon]

    def zones_covering_position(
        self,
        position: Tuple[float, float, float],
        echelon: Optional[DefenseEchelon] = None,
    ) -> List[DefenseZone]:
        """Return zones covering a target position for tactical prioritization."""
        px, py, pz = position
        zones = self.list_zones(echelon=echelon)
        covered: List[DefenseZone] = []
        for zone in zones:
            zx, zy, zz = zone.center
            distance = math.dist((px, py, pz), (zx, zy, zz))
            if distance <= zone.radius_m:
                covered.append(zone)
        return covered

    def get_coverage_report(self) -> Dict[str, object]:
        """Build coverage metrics for operator mission displays."""
        zones = list(self._zones.values())
        by_echelon = Counter(zone.echelon.value for zone in zones)
        defended_assets = sorted({zone.defended_asset for zone in zones})
        return {
            "zones_total": len(zones),
            "zones_by_echelon": dict(by_echelon),
            "max_radius_m": max((zone.radius_m for zone in zones), default=0.0),
            "defended_assets": defended_assets,
        }

