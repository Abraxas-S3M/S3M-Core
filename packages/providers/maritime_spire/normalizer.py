"""Normalizer for Spire maritime satellite and terrestrial AIS payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.maritime.models import NormalizedVesselTrack


class SpireNormalizer:
    """Normalize nested Spire vessel position structures."""

    def __init__(self, provider_id: str = "maritime-spire", provider_name: str = "Spire Maritime") -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name

    def _parse_dt(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    def classify_collection_type(self, vessel: dict[str, Any]) -> str:
        history = vessel.get("history", [])
        if not history and vessel.get("recent_collection_types"):
            history = [{"collection_type": item} for item in vessel.get("recent_collection_types", [])]
        latest_type = str(vessel.get("position", {}).get("collection_type", "")).lower()
        observed = {latest_type} if latest_type else set()
        for rec in history:
            ctype = str(rec.get("collection_type", "")).lower()
            if ctype:
                observed.add(ctype)
        if "satellite" in observed and "terrestrial" in observed:
            return "mixed"
        if "satellite" in observed:
            return "satellite"
        return "terrestrial"

    def _has_recent_terrestrial(self, vessel: dict[str, Any], within_hours: int = 6) -> bool:
        latest_ts = self._parse_dt(vessel.get("position", {}).get("timestamp"))
        history = vessel.get("history", [])
        for rec in history:
            ctype = str(rec.get("collection_type", "")).lower()
            if ctype != "terrestrial":
                continue
            ts = self._parse_dt(rec.get("timestamp"))
            age = (latest_ts - ts).total_seconds() / 3600.0
            if age <= within_hours:
                return True
        return False

    def normalize_vessel(self, vessel: dict[str, Any], zone_name: str | None = None) -> NormalizedVesselTrack:
        pos = vessel.get("position", {})
        vessel_meta = vessel.get("vessel", {})
        collection_type = str(pos.get("collection_type", "terrestrial")).lower()
        recent_terrestrial = self._has_recent_terrestrial(vessel, within_hours=6)
        is_dark = collection_type == "satellite" and not recent_terrestrial
        confidence = 0.85 if is_dark else 0.95
        tags = [f"collection:{collection_type}"]
        if collection_type == "satellite":
            tags.append("satellite_ais")
        zone_name = zone_name or vessel.get("_zone")
        if zone_name:
            tags.append(f"zone:{zone_name}")

        # Tactical context: satellite AIS extends surveillance beyond coastal receivers.
        provenance = Provenance(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            fetched_at=datetime.now(timezone.utc),
            raw_id=str(vessel.get("mmsi", "")),
            confidence=confidence,
            classification="UNCLASSIFIED",
        )

        return NormalizedVesselTrack(
            mmsi=str(vessel.get("mmsi", "")),
            imo=str(vessel_meta.get("imo")) if vessel_meta.get("imo") else None,
            vessel_name=str(vessel.get("name", "")),
            vessel_type=str(vessel.get("ship_type", "Unknown")),
            flag_state=str(vessel.get("flag", "")),
            speed_knots=float(pos.get("speed", 0.0) or 0.0),
            course_deg=float(pos.get("course", 0.0) or 0.0),
            heading_deg=float(pos.get("heading", 0.0) or 0.0),
            destination=vessel.get("destination"),
            nav_status="underway using engine",
            draught_m=float(vessel_meta.get("draught", 0.0) or 0.0) or None,
            length_m=float(vessel_meta.get("length", 0.0) or 0.0) or None,
            is_dark=is_dark,
            provenance=provenance,
            timestamp=self._parse_dt(pos.get("timestamp")),
            geo_point=GeoPoint(
                lat=float(pos.get("latitude", 0.0) or 0.0),
                lon=float(pos.get("longitude", 0.0) or 0.0),
            ),
            tags=tags,
            raw_data_ref=str(vessel.get("mmsi", "")),
        )

    def normalize_batch(self, vessels: list[dict[str, Any]], zone_name: str | None = None) -> list[NormalizedVesselTrack]:
        return [self.normalize_vessel(v, zone_name=zone_name) for v in vessels]
