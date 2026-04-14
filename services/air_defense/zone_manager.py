"""Zone manager for layered air-defense geometry."""

from __future__ import annotations

from services.air_defense.models import DefenseEchelon, DefenseZone


class ZoneManager:
    """Creates and manages tactical defense echelons around an asset."""

    def __init__(self) -> None:
        self._zones: dict[str, DefenseZone] = {}

    def get_zone(self, zone_id: str) -> DefenseZone | None:
        """Fetch zone by identifier."""
        return self._zones.get(zone_id)

    def list_zones(self) -> list[DefenseZone]:
        """List all managed zones."""
        return list(self._zones.values())

    def create_standard_echelons(
        self, center: tuple[float, float, float]
    ) -> list[DefenseZone]:
        """Create default 4-layer tactical defense ring geometry."""
        zones = [
            DefenseZone(
                echelon=DefenseEchelon.CLOSE,
                center=center,
                inner_radius_m=0,
                outer_radius_m=4000,
                min_altitude_m=0,
                max_altitude_m=3000,
            ),
            DefenseZone(
                echelon=DefenseEchelon.SHORT,
                center=center,
                inner_radius_m=4000,
                outer_radius_m=18000,
                min_altitude_m=0,
                max_altitude_m=10000,
            ),
            DefenseZone(
                echelon=DefenseEchelon.MEDIUM,
                center=center,
                inner_radius_m=18000,
                outer_radius_m=50000,
                min_altitude_m=0,
                max_altitude_m=25000,
            ),
            DefenseZone(
                echelon=DefenseEchelon.EXTENDED,
                center=center,
                inner_radius_m=50000,
                outer_radius_m=80000,
                min_altitude_m=0,
                max_altitude_m=40000,
            ),
        ]
        self._zones = {zone.zone_id: zone for zone in zones}
        return zones

    def assign_effector_to_zone(self, zone_id: str, effector_id: str) -> None:
        """Associate an effector with a defensive ring."""
        zone = self.get_zone(zone_id)
        if zone is None:
            return
        if effector_id not in zone.assigned_effector_ids:
            zone.assigned_effector_ids.append(effector_id)

    def find_zones_for_target(
        self, target_position: tuple[float, float, float]
    ) -> list[DefenseZone]:
        """Return all zones that contain the target geometry."""
        zones = [zone for zone in self.list_zones() if zone.contains_point(target_position)]
        return sorted(zones, key=lambda zone: zone.outer_radius_m)

    def get_coverage_report(self) -> dict[str, dict[str, int]]:
        """Produce echelon coverage totals for tactical readiness views."""
        report: dict[str, dict[str, int]] = {}
        for zone in self.list_zones():
            key = zone.echelon.value
            report[key] = {
                "zone_id": zone.zone_id,
                "total_effectors": len(zone.assigned_effector_ids),
            }
        return report

