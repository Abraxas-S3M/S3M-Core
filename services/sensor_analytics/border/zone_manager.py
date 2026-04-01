"""Zone manager for Saudi maritime and border surveillance sectors."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml

from services.sensor_analytics.models import BorderZone


class ZoneManager:
    """Load and query mission zones for tactical border awareness."""

    def __init__(self, zones_config: str = "configs/sensor-analytics/zones.yaml") -> None:
        self.zones_config = zones_config
        self.zones: List[BorderZone] = []
        self.zone_alert_counts: Dict[str, int] = {}
        self.zone_vessel_counts: Dict[str, int] = {}
        self.load_zones()

    def load_zones(self) -> List[BorderZone]:
        path = Path(self.zones_config)
        if not path.exists():
            self.zones = []
            return self.zones
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        zones_raw = payload.get("zones", [])
        zones: List[BorderZone] = []
        for raw in zones_raw:
            poly = [tuple(v) for v in raw.get("polygon", [])]
            zones.append(
                BorderZone(
                    zone_id=str(raw.get("id", "")),
                    name=str(raw.get("name", "")),
                    zone_type=str(raw.get("zone_type", "maritime_eez")),
                    polygon=poly,
                    threat_level=str(raw.get("threat_level", "low")),
                    active_sensors=list(raw.get("active_sensors", [])),
                )
            )
        self.zones = zones
        return zones

    def get_zone(self, zone_id: str) -> Optional[BorderZone]:
        for zone in self.zones:
            if zone.zone_id == zone_id:
                return zone
        return None

    def get_zones(self, zone_type: Optional[str] = None) -> List[BorderZone]:
        if not zone_type:
            return list(self.zones)
        return [zone for zone in self.zones if zone.zone_type == zone_type]

    def check_position(self, lat: float, lon: float) -> List[BorderZone]:
        return [zone for zone in self.zones if zone.contains_point(lat, lon)]

    def update_threat_level(self, zone_id: str, level: str) -> None:
        zone = self.get_zone(zone_id)
        if zone is None:
            return
        zone.threat_level = level

    def get_zone_statistics(self) -> Dict[str, Dict[str, int]]:
        stats: Dict[str, Dict[str, int]] = {}
        for zone in self.zones:
            stats[zone.zone_id] = {
                "alerts": self.zone_alert_counts.get(zone.zone_id, 0),
                "vessels": self.zone_vessel_counts.get(zone.zone_id, 0),
            }
        return stats
