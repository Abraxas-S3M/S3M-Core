"""Echeloned defense-zone management for layered air-defense geometry.

Military context:
Layered zones represent outer-to-inner interception rings used by command and
control nodes to preserve high-value interceptors and enforce doctrine.
"""

from __future__ import annotations

from threading import RLock
from typing import Dict, List, Optional, Tuple

from services.air_defense.models import DefenseEchelon, DefenseZone


class DefenseZoneManager:
    """Thread-safe store for layered defense zones and overlap calculations."""

    ECHELON_RANGE_BANDS_KM = {
        DefenseEchelon.CLOSE: (0.0, 10.0),
        DefenseEchelon.SHORT: (10.0, 20.0),
        DefenseEchelon.MEDIUM: (20.0, 40.0),
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._zones: Dict[str, DefenseZone] = {}

    def register_zone(self, zone: DefenseZone, *, replace_existing: bool = False) -> DefenseZone:
        """Register or replace a defense zone."""
        with self._lock:
            if zone.zone_id in self._zones and not replace_existing:
                raise ValueError(f"zone already exists: {zone.zone_id}")
            self._zones[zone.zone_id] = zone
            return zone

    def remove_zone(self, zone_id: str) -> Optional[DefenseZone]:
        """Delete zone by ID."""
        with self._lock:
            return self._zones.pop(str(zone_id), None)

    def get_zone(self, zone_id: str) -> Optional[DefenseZone]:
        """Fetch one zone by ID."""
        with self._lock:
            return self._zones.get(str(zone_id))

    def list_zones(self, *, echelon: Optional[DefenseEchelon] = None, unit_id: Optional[str] = None) -> List[DefenseZone]:
        """List zones with optional echelon or unit filters."""
        with self._lock:
            zones = list(self._zones.values())
            if echelon is not None:
                zones = [z for z in zones if z.echelon == echelon]
            if unit_id is not None:
                zones = [z for z in zones if z.unit_id == unit_id]
            return sorted(zones, key=lambda zone: zone.zone_id)

    def create_echeloned_zones(
        self,
        *,
        unit_id: str,
        center: Tuple[float, float],
        name_prefix_en: str,
        name_prefix_ar: str,
    ) -> List[DefenseZone]:
        """Create close/short/medium layered zones and register them."""
        created: List[DefenseZone] = []
        for echelon in (DefenseEchelon.CLOSE, DefenseEchelon.SHORT, DefenseEchelon.MEDIUM):
            min_radius, max_radius = self.ECHELON_RANGE_BANDS_KM[echelon]
            zone = DefenseZone(
                zone_id=f"{unit_id}-{echelon.value}-zone",
                name_en=f"{name_prefix_en} {echelon.value.title()} Layer",
                name_ar=f"{name_prefix_ar} {echelon.value.title()} Layer",
                echelon=echelon,
                center=center,
                min_radius_km=min_radius,
                radius_km=max_radius,
                unit_id=unit_id,
            )
            self.register_zone(zone=zone, replace_existing=True)
            created.append(zone)
        return created

    def point_in_zone(self, x_km: float, y_km: float, altitude_m: float, zone_id: str) -> bool:
        """Check if a point belongs to the specified zone."""
        zone = self.get_zone(zone_id)
        if zone is None:
            return False
        return zone.contains_point(x_km=x_km, y_km=y_km, altitude_m=altitude_m)

    def get_covering_zones(self, x_km: float, y_km: float, altitude_m: float) -> List[DefenseZone]:
        """Return all zones that include a 3D point."""
        with self._lock:
            matches = [zone for zone in self._zones.values() if zone.contains_point(x_km=x_km, y_km=y_km, altitude_m=altitude_m)]
            return sorted(matches, key=lambda zone: zone.zone_id)

    def classify_echelon_for_distance(self, distance_km: float) -> Optional[DefenseEchelon]:
        """Classify distance into doctrinal close/short/medium defense bands."""
        value = float(distance_km)
        for echelon, (min_radius, max_radius) in self.ECHELON_RANGE_BANDS_KM.items():
            if min_radius <= value <= max_radius:
                return echelon
        return None

    def compute_coverage_overlap(
        self,
        zone_a_id: str,
        zone_b_id: str,
        *,
        sample_resolution: int = 120,
    ) -> Dict[str, float]:
        """Estimate overlap area between two zones using deterministic sampling."""
        zone_a = self.get_zone(zone_a_id)
        zone_b = self.get_zone(zone_b_id)
        if zone_a is None or zone_b is None:
            return {"overlap_km2": 0.0, "overlap_ratio": 0.0}

        overlap_altitude_min = max(zone_a.min_altitude_m, zone_b.min_altitude_m)
        overlap_altitude_max = min(zone_a.max_altitude_m, zone_b.max_altitude_m)
        if overlap_altitude_max <= overlap_altitude_min:
            return {"overlap_km2": 0.0, "overlap_ratio": 0.0}

        x_min = max(zone_a.center[0] - zone_a.radius_km, zone_b.center[0] - zone_b.radius_km)
        x_max = min(zone_a.center[0] + zone_a.radius_km, zone_b.center[0] + zone_b.radius_km)
        y_min = max(zone_a.center[1] - zone_a.radius_km, zone_b.center[1] - zone_b.radius_km)
        y_max = min(zone_a.center[1] + zone_a.radius_km, zone_b.center[1] + zone_b.radius_km)

        if x_max <= x_min or y_max <= y_min:
            return {"overlap_km2": 0.0, "overlap_ratio": 0.0}

        resolution = max(20, int(sample_resolution))
        step_x = (x_max - x_min) / resolution
        step_y = (y_max - y_min) / resolution
        if step_x <= 0 or step_y <= 0:
            return {"overlap_km2": 0.0, "overlap_ratio": 0.0}

        altitude_probe = (overlap_altitude_min + overlap_altitude_max) * 0.5
        overlap_count = 0
        total_cells = resolution * resolution

        # Tactical context: deterministic fixed-grid overlap allows reproducible
        # command post planning without stochastic variation across runs.
        for row in range(resolution):
            sample_y = y_min + (row + 0.5) * step_y
            for col in range(resolution):
                sample_x = x_min + (col + 0.5) * step_x
                if zone_a.contains_point(sample_x, sample_y, altitude_probe) and zone_b.contains_point(sample_x, sample_y, altitude_probe):
                    overlap_count += 1

        overlap_area = overlap_count * step_x * step_y
        min_area = min(zone_a.area_km2(), zone_b.area_km2())
        overlap_ratio = 0.0 if min_area <= 0.0 else min(1.0, overlap_area / min_area)
        return {"overlap_km2": max(0.0, overlap_area), "overlap_ratio": overlap_ratio, "samples": float(total_cells)}
