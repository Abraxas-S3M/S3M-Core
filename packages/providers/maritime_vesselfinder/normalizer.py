"""Normalizer for VesselFinder AIS and port-arrival payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.maritime.models import NormalizedVesselTrack

from .config import VesselFinderConfig


class VesselFinderNormalizer:
    """Convert VesselFinder payloads to NormalizedVesselTrack."""

    def __init__(self, provider_id: str = "maritime-vesselfinder", provider_name: str = "VesselFinder") -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.config = VesselFinderConfig()

    def _parse_dt(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        text = value.strip()
        if " " in text and "T" not in text and len(text) > 10:
            text = text.replace(" ", "T")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    def _parse_eta(self, eta_text: str | None) -> datetime | None:
        if not eta_text:
            return None
        text = eta_text.strip()
        if len(text) != 9 or " " not in text:
            return None
        try:
            mmdd, hm = text.split(" ")
            month = int(mmdd[:2])
            day = int(mmdd[2:])
            hour = int(hm[:2])
            minute = int(hm[2:])
            now = datetime.now(timezone.utc)
            return datetime(now.year, month, day, hour, minute, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            return None

    def _f(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _map_ais_type(self, ais_type: int) -> str:
        for start, end, name in self.config.ais_type_map:
            if start <= ais_type <= end:
                return name
        return "Unknown"

    def normalize_vessel(self, vessel_ais: dict[str, Any]) -> NormalizedVesselTrack:
        ais_type = int(vessel_ais.get("TYPE", 0) or 0)
        length = self._f(vessel_ais.get("A"), 0.0) + self._f(vessel_ais.get("B"), 0.0)
        beam = self._f(vessel_ais.get("C"), 0.0) + self._f(vessel_ais.get("D"), 0.0)
        # Tactical context: terrestrial AIS still carries high confidence for near-shore COP.
        provenance = Provenance(
            provider_id=self.provider_id,
            provider_name=self.provider_name,
            fetched_at=datetime.now(timezone.utc),
            raw_id=str(vessel_ais.get("MMSI", "")),
            confidence=0.90,
            classification="UNCLASSIFIED",
        )
        return NormalizedVesselTrack(
            mmsi=str(vessel_ais.get("MMSI", "")),
            imo=str(vessel_ais.get("IMO")) if vessel_ais.get("IMO") else None,
            vessel_name=str(vessel_ais.get("NAME", "")),
            vessel_type=self._map_ais_type(ais_type),
            flag_state=str(vessel_ais.get("FLAG", "")),
            speed_knots=self._f(vessel_ais.get("SPEED"), 0.0),
            course_deg=self._f(vessel_ais.get("COURSE"), 0.0),
            heading_deg=self._f(vessel_ais.get("HEADING"), 0.0),
            destination=(str(vessel_ais.get("DESTINATION")).strip() if vessel_ais.get("DESTINATION") else None),
            eta=self._parse_eta(vessel_ais.get("ETA")),
            nav_status=str(vessel_ais.get("NAVSTAT", "")),
            draught_m=self._f(vessel_ais.get("DRAUGHT"), 0.0) or None,
            length_m=length or None,
            timestamp=self._parse_dt(vessel_ais.get("TIMESTAMP")),
            geo_point=GeoPoint(
                lat=self._f(vessel_ais.get("LATITUDE"), 0.0),
                lon=self._f(vessel_ais.get("LONGITUDE"), 0.0),
            ),
            provenance=provenance,
            tags=[
                self._map_ais_type(ais_type).lower(),
                f"beam_m:{int(beam) if beam else 0}",
                "source:terrestrial_ais",
            ],
            raw_data_ref=str(vessel_ais.get("MMSI", "")),
        )

    def normalize_batch(self, vessels: list[dict[str, Any]]) -> list[NormalizedVesselTrack]:
        return [self.normalize_vessel(item.get("AIS", item)) for item in vessels]

    def normalize_port_arrivals(self, arrivals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in arrivals:
            eta = self._parse_eta(item.get("ETA"))
            normalized.append(
                {
                    "mmsi": str(item.get("MMSI", "")),
                    "vessel_name": item.get("NAME"),
                    "port": item.get("PORT"),
                    "eta": eta.isoformat() if eta else None,
                }
            )
        return normalized
