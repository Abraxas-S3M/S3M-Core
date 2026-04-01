"""Normalizer for MarineTraffic vessel, event, and AIS-gap payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.maritime.models import NormalizedVesselTrack

from .config import MarineTrafficConfig


class MarineTrafficNormalizer:
    """Convert MarineTraffic responses into normalized maritime records."""

    def __init__(self, provider_id: str = "maritime-marinetraffic", provider_name: str = "MarineTraffic") -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.config = MarineTrafficConfig()

    def _parse_dt(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        normalized = str(value).replace("Z", "+00:00")
        if " " in normalized and "T" not in normalized:
            normalized = normalized.replace(" ", "T")
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    def _float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _ship_type_name(self, code: Any) -> str:
        try:
            key = int(code)
        except (TypeError, ValueError):
            return "Unknown"
        return self.config.ship_type_names.get(key, "Unknown")

    def _nav_status_name(self, code: Any) -> str:
        try:
            key = int(code)
        except (TypeError, ValueError):
            return "unknown"
        return self.config.nav_status_names.get(key, "unknown")

    def normalize_vessel(self, vessel: dict[str, Any]) -> NormalizedVesselTrack:
        speed_knots = self._float(vessel.get("SPEED"), 0.0) / self.config.speed_divisor
        draught_m = self._float(vessel.get("DRAUGHT"), 0.0) / self.config.draught_divisor
        ship_type_code = vessel.get("SHIPTYPE")
        ship_type_name = vessel.get("TYPE_NAME") or self._ship_type_name(ship_type_code)
        timestamp = self._parse_dt(vessel.get("TIMESTAMP"))
        tags = [
            ship_type_name.lower().replace(" ", "_"),
            f"flag:{str(vessel.get('FLAG', 'unknown')).upper()}",
            f"dsrc:{str(vessel.get('DSRC', 'unknown')).lower()}",
        ]
        zone = vessel.get("_zone") or vessel.get("ZONE_NAME")
        if zone:
            tags.append(f"zone:{zone}")

        # Tactical context: direct AIS tracks are high-confidence inputs for coastal COP.
        provenance = Provenance(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            fetched_at=datetime.now(timezone.utc),
            raw_id=str(vessel.get("SHIP_ID") or vessel.get("MMSI") or ""),
            confidence=0.95,
            classification="UNCLASSIFIED",
        )
        return NormalizedVesselTrack(
            mmsi=str(vessel.get("MMSI", "")),
            imo=str(vessel.get("IMO")) if vessel.get("IMO") else None,
            vessel_name=str(vessel.get("SHIPNAME", "")),
            vessel_type=ship_type_name,
            flag_state=str(vessel.get("FLAG", "")),
            speed_knots=speed_knots,
            course_deg=self._float(vessel.get("COURSE"), 0.0),
            heading_deg=self._float(vessel.get("HEADING"), 0.0),
            destination=(str(vessel.get("DESTINATION")).strip() if vessel.get("DESTINATION") else None),
            eta=self._parse_dt(vessel.get("ETA")) if vessel.get("ETA") else None,
            nav_status=self._nav_status_name(vessel.get("STATUS")),
            draught_m=draught_m if draught_m > 0 else None,
            length_m=self._float(vessel.get("LENGTH"), 0.0) or None,
            is_dark=False,
            provenance=provenance,
            timestamp=timestamp,
            geo_point=GeoPoint(
                lat=self._float(vessel.get("LAT"), 0.0),
                lon=self._float(vessel.get("LON"), 0.0),
            ),
            tags=tags,
            raw_data_ref=str(vessel.get("SHIP_ID") or vessel.get("MMSI") or ""),
        )

    def normalize_batch(self, vessels: list[dict[str, Any]]) -> list[NormalizedVesselTrack]:
        return [self.normalize_vessel(item) for item in vessels]

    def normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_code = int(event.get("EVENT_TYPE", 0) or 0)
        event_type = self.config.event_type_names.get(event_code, f"event_{event_code}")
        return {
            "mmsi": str(event.get("MMSI", "")),
            "event_type": event_type,
            "timestamp": self._parse_dt(event.get("TIMESTAMP")).isoformat(),
            "position": {
                "lat": self._float(event.get("LAT"), 0.0),
                "lon": self._float(event.get("LON"), 0.0),
            },
            "port_name": event.get("PORT_NAME"),
            "detail": event.get("DETAIL") or event.get("EVENT_DESC"),
        }

    def detect_ais_gaps(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        starts: dict[str, list[dict[str, Any]]] = {}
        gaps: list[dict[str, Any]] = []
        sorted_events = sorted(events, key=lambda e: self._parse_dt(e.get("TIMESTAMP")))
        for event in sorted_events:
            mmsi = str(event.get("MMSI", ""))
            code = int(event.get("EVENT_TYPE", 0) or 0)
            if code == 19:
                starts.setdefault(mmsi, []).append(event)
            elif code == 20 and starts.get(mmsi):
                start = starts[mmsi].pop(0)
                start_ts = self._parse_dt(start.get("TIMESTAMP"))
                end_ts = self._parse_dt(event.get("TIMESTAMP"))
                duration = max(0.0, (end_ts - start_ts).total_seconds() / 3600.0)
                gaps.append(
                    {
                        "mmsi": mmsi,
                        "gap_start": start_ts.isoformat(),
                        "gap_end": end_ts.isoformat(),
                        "duration_hours": round(duration, 2),
                        "last_known_position": {
                            "lat": self._float(start.get("LAT"), 0.0),
                            "lon": self._float(start.get("LON"), 0.0),
                        },
                        "dark_vessel_flag": duration > 1.0,
                    }
                )
        return gaps
