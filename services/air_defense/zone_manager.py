"""Echeloned defense zone spatial management.

Military context:
Implements the Krechet layered coverage concept: close-range (0-10km),
short-range (10-20km), medium-range (20-40km), and extended interceptor-drone
coverage (up to 40km). Zones determine which effectors are candidates for
target allocation based on where the threat enters the defended airspace.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from services.air_defense.models import DefenseEchelon, DefenseZone


# Default echelon boundaries matching Krechet 9C905 coverage diagram
ECHELON_DEFAULTS: Dict[DefenseEchelon, Tuple[float, float, float, float]] = {
    # (inner_radius_m, outer_radius_m, min_alt_m, max_alt_m)
    DefenseEchelon.CLOSE: (0, 10_000, 0, 3_000),
    DefenseEchelon.SHORT: (10_000, 20_000, 0, 8_000),
    DefenseEchelon.MEDIUM: (20_000, 40_000, 0, 15_000),
    DefenseEchelon.EXTENDED: (20_000, 40_000, 0, 12_000),
}


class ZoneManager:
    """Manages echeloned defense zones around defended assets."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._zones: Dict[str, DefenseZone] = {}

    def create_zone(self, zone: DefenseZone) -> DefenseZone:
        """Register a new defense zone."""
        if not isinstance(zone, DefenseZone):
            raise ValueError("zone must be a DefenseZone instance")
        with self._lock:
            self._zones[zone.zone_id] = zone
        return zone

    def create_standard_echelons(
        self,
        center: Tuple[float, float, float],
        defended_asset_name: str = "Protected Site",
        defended_asset_name_ar: str = "الموقع المحمي",
    ) -> List[DefenseZone]:
        """Create standard close/short/medium/extended echelon zones around a point."""
        if len(center) != 3:
            raise ValueError("center must be a 3D coordinate tuple")
        if not defended_asset_name.strip():
            raise ValueError("defended_asset_name must be non-empty")
        if not defended_asset_name_ar.strip():
            raise ValueError("defended_asset_name_ar must be non-empty")

        zones: List[DefenseZone] = []
        echelon_names = {
            DefenseEchelon.CLOSE: ("Close defense zone", "منطقة الدفاع القريبة"),
            DefenseEchelon.SHORT: ("Short-range defense zone", "منطقة الدفاع قصيرة المدى"),
            DefenseEchelon.MEDIUM: ("Medium-range defense zone", "منطقة الدفاع متوسطة المدى"),
            DefenseEchelon.EXTENDED: ("Extended interceptor zone", "منطقة الاعتراض الممتدة"),
        }
        priorities = {"close": 1, "short": 2, "medium": 3, "extended": 4}

        for echelon, (inner_r, outer_r, min_alt, max_alt) in ECHELON_DEFAULTS.items():
            name_en, name_ar = echelon_names[echelon]
            zone = DefenseZone(
                name_en=f"{name_en} - {defended_asset_name}",
                name_ar=f"{name_ar} - {defended_asset_name_ar}",
                echelon=echelon,
                center=center,
                inner_radius_m=inner_r,
                outer_radius_m=outer_r,
                min_altitude_m=min_alt,
                max_altitude_m=max_alt,
                priority=priorities[echelon.value],
            )
            zones.append(self.create_zone(zone))
        return zones

    def remove_zone(self, zone_id: str) -> bool:
        if not zone_id:
            return False
        with self._lock:
            return self._zones.pop(zone_id, None) is not None

    def get_zone(self, zone_id: str) -> Optional[DefenseZone]:
        if not zone_id:
            return None
        with self._lock:
            return self._zones.get(zone_id)

    def list_zones(
        self, echelon: Optional[DefenseEchelon] = None, active_only: bool = True
    ) -> List[DefenseZone]:
        with self._lock:
            zones = list(self._zones.values())
        if echelon is not None:
            zones = [zone for zone in zones if zone.echelon == echelon]
        if active_only:
            zones = [zone for zone in zones if zone.active]
        return sorted(zones, key=lambda zone: zone.priority)

    def find_zones_for_target(
        self, target_position: Tuple[float, float, float]
    ) -> List[DefenseZone]:
        """Return active zones containing the target, sorted with outermost first."""
        with self._lock:
            zones = [
                zone
                for zone in self._zones.values()
                if zone.active and zone.contains_point(target_position)
            ]
        # Krechet doctrine: engage at maximum range first, fall back inward.
        return sorted(zones, key=lambda zone: zone.priority, reverse=True)

    def assign_effector_to_zone(self, zone_id: str, effector_id: str) -> bool:
        if not zone_id or not effector_id:
            return False
        with self._lock:
            zone = self._zones.get(zone_id)
            if zone is None:
                return False
            if effector_id not in zone.assigned_effector_ids:
                zone.assigned_effector_ids.append(effector_id)
            return True

    def get_coverage_report(self) -> Dict[str, Any]:
        """Return coverage summary across all echelons."""
        with self._lock:
            zones = list(self._zones.values())

        report: Dict[str, Any] = {}
        for echelon in DefenseEchelon:
            echelon_zones = [zone for zone in zones if zone.echelon == echelon and zone.active]
            report[echelon.value] = {
                "zones": len(echelon_zones),
                "total_effectors": sum(
                    len(zone.assigned_effector_ids) for zone in echelon_zones
                ),
                "outer_radius_m": max(
                    (zone.outer_radius_m for zone in echelon_zones), default=0
                ),
            }
        return report
