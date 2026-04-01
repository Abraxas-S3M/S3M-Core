"""AIS vessel tracker for maritime domain awareness in Layer 09."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Dict, List, Optional

from services.sensor_analytics.ais.parser import AISParser
from services.sensor_analytics.geospatial.processor import GeospatialProcessor
from services.sensor_analytics.models import AISMessage, AISVessel, BorderZone, SARDetection, VesselClassification


def _classification_from_type(vessel_type: int) -> VesselClassification:
    if vessel_type in {70, 71, 72, 73, 74, 79}:
        return VesselClassification.CARGO
    if vessel_type in {80, 81, 82, 83, 84, 89}:
        return VesselClassification.TANKER
    if vessel_type in {30, 31, 32}:
        return VesselClassification.FISHING
    if vessel_type in {50, 51, 52, 53, 54, 55}:
        return VesselClassification.PATROL
    if vessel_type in {60, 61, 62, 69}:
        return VesselClassification.PASSENGER
    if vessel_type in {36, 37}:
        return VesselClassification.YACHT
    return VesselClassification.UNKNOWN


class AISTracker:
    """Tracks AIS traffic with risk scoring for Saudi maritime surveillance."""

    def __init__(self, max_vessels: int = 10000) -> None:
        self.max_vessels = max_vessels
        self.parser = AISParser()
        self.geo = GeospatialProcessor()
        self.vessels: Dict[str, AISVessel] = {}
        self._restricted_zone_ids: set[str] = set()

    def update(self, message: AISMessage) -> None:
        vessel = self.vessels.get(message.mmsi)
        now = message.timestamp
        if vessel is None:
            if len(self.vessels) >= self.max_vessels:
                oldest_key = min(self.vessels.keys(), key=lambda k: self.vessels[k].last_seen)
                del self.vessels[oldest_key]
            vessel = AISVessel(
                mmsi=message.mmsi,
                vessel_name=message.vessel_name or f"Vessel-{message.mmsi}",
                classification=_classification_from_type(message.vessel_type),
                flag_state="UNKNOWN",
                imo_number=None,
                length_meters=0.0,
                beam_meters=0.0,
                last_position=(message.lat, message.lon),
                last_speed_knots=float(message.speed_knots),
                last_heading_deg=float(message.heading_deg),
                last_seen=now,
                positions_count=0,
                ais_active=True,
                risk_score=0.0,
                track=[],
            )
            self.vessels[message.mmsi] = vessel

        track_entry = {
            "timestamp": now.isoformat(),
            "lat": float(message.lat),
            "lon": float(message.lon),
            "speed_knots": float(message.speed_knots),
            "course_deg": float(message.course_deg),
            "heading_deg": float(message.heading_deg),
        }
        vessel.track.append(track_entry)
        if len(vessel.track) > 100:
            vessel.track = vessel.track[-100:]
        vessel.positions_count = len(vessel.track)
        vessel.last_position = (float(message.lat), float(message.lon))
        vessel.last_speed_knots = float(message.speed_knots)
        vessel.last_heading_deg = float(message.heading_deg)
        vessel.last_seen = now
        vessel.ais_active = True
        if message.vessel_name:
            vessel.vessel_name = message.vessel_name
        vessel.classification = _classification_from_type(message.vessel_type)
        vessel.risk_score = self.compute_risk_score(vessel)

    def ingest_file(self, filepath: str) -> None:
        for msg in self.parser.parse_file(filepath):
            self.update(msg)

    def get_vessel(self, mmsi: str) -> Optional[AISVessel]:
        return self.vessels.get(mmsi)

    def get_all_vessels(self, classification: VesselClassification = None) -> List[AISVessel]:
        vessels = list(self.vessels.values())
        if classification is not None:
            vessels = [v for v in vessels if v.classification == classification]
        return vessels

    def get_vessels_in_zone(self, zone: BorderZone) -> List[AISVessel]:
        return [v for v in self.vessels.values() if zone.contains_point(v.last_position[0], v.last_position[1])]

    def get_dark_vessels(self) -> List[AISVessel]:
        output: List[AISVessel] = []
        now = datetime.now(timezone.utc)
        for vessel in self.vessels.values():
            age = (now - vessel.last_seen).total_seconds() / 3600.0
            if age > 1.0 and vessel.positions_count > 0:
                vessel.ais_active = False
                vessel.risk_score = self.compute_risk_score(vessel)
                output.append(vessel)
        return output

    def compute_risk_score(self, vessel: AISVessel) -> float:
        score = 0.0
        if vessel.is_dark():
            score += 0.4
        if vessel.last_speed_knots > 40.0:
            score += 0.2
        if getattr(vessel, "in_restricted_zone", False):
            score += 0.2
        if vessel.flag_state.upper() in {"", "UNKNOWN"}:
            score += 0.1
        if len(vessel.track) >= 3:
            h1 = float(vessel.track[-1]["heading_deg"])
            h2 = float(vessel.track[-2]["heading_deg"])
            h3 = float(vessel.track[-3]["heading_deg"])
            if abs(h1 - h2) > 45 and abs(h2 - h3) > 45:
                score += 0.1
        return max(0.0, min(1.0, score))

    def match_sar_detection(self, detection: SARDetection, radius_km: float = 5.0) -> Optional[AISVessel]:
        best: Optional[AISVessel] = None
        best_dist = float("inf")
        dlat, dlon = detection.geo_position
        for vessel in self.vessels.values():
            vlat, vlon = vessel.last_position
            dist = self.geo.haversine_distance(dlat, dlon, vlat, vlon)
            if dist <= radius_km and dist < best_dist:
                best = vessel
                best_dist = dist
        return best

    def get_statistics(self) -> dict:
        by_class: Dict[str, int] = {}
        for vessel in self.vessels.values():
            key = vessel.classification.value
            by_class[key] = by_class.get(key, 0) + 1
        dark_count = len(self.get_dark_vessels())
        return {
            "total_vessels": len(self.vessels),
            "by_classification": by_class,
            "dark_count": dark_count,
            "restricted_zone_count": len([v for v in self.vessels.values() if getattr(v, "in_restricted_zone", False)]),
        }

    def export_tracks(self, filepath: str) -> None:
        features: List[dict] = []
        for vessel in self.vessels.values():
            coords = [[point["lon"], point["lat"]] for point in vessel.track]
            if not coords:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "mmsi": vessel.mmsi,
                        "name": vessel.vessel_name,
                        "classification": vessel.classification.value,
                    },
                }
            )
        collection = {"type": "FeatureCollection", "features": features}
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(collection, handle, indent=2)
