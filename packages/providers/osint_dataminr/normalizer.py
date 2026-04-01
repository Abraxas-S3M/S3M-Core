"""Normalize Dataminr alerts into S3M global event records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.event_intel.models import NormalizedGlobalEvent


class DataminrNormalizer:
    _severity_map = {"flash": "critical", "urgentAlert": "high", "alert": "medium"}

    def _event_type(self, alert: dict[str, Any]) -> str:
        categories = alert.get("categories", [])
        text = " ".join(str(c.get("name", "")) for c in categories).lower()
        if "cyber" in text:
            return "cyber_event"
        if "maritime" in text:
            return "maritime_incident"
        if "protest" in text:
            return "protest"
        if "military" in text or "conflict" in text:
            return "conflict"
        return "global_event"

    def normalize_alert(self, alert: dict[str, Any]) -> NormalizedGlobalEvent:
        alert_type = str(alert.get("alertType", "alert"))
        location = alert.get("eventLocation", {}) if isinstance(alert.get("eventLocation"), dict) else {}
        entity_name = str((alert.get("metadata", {}) or {}).get("entityName", "")).strip()
        header_terms = list(alert.get("headerTerms", []))
        actors = [term for term in header_terms if isinstance(term, str)]
        if entity_name:
            actors.append(entity_name)

        sentiment = -0.7 if alert_type in {"flash", "urgentAlert"} else -0.3
        event = NormalizedGlobalEvent(
            event_type=self._event_type(alert),
            actors=actors,
            country=str(alert.get("country", "")),
            region=str(alert.get("region", "middle-east")),
            source_count=1,
            sentiment_score=sentiment,
            tags=[
                f"watchlist:{alert.get('watchlistName', 'unknown')}",
                f"alert_type:{alert_type}",
                *[str(c.get("name")) for c in alert.get("categories", []) if c.get("name")],
                *[str(s.get("name")) for s in alert.get("sectors", []) if s.get("name")],
            ],
            provenance=Provenance(
                provider_id="osint-dataminr",
                provider_name="Dataminr",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(alert.get("alertId", "unknown")),
                confidence=0.70,
                classification="UNCLASSIFIED",
            ),
        )
        event.raw_data_ref = str(alert.get("alertId", ""))
        if "latitude" in location and "longitude" in location:
            event.geo_point = GeoPoint(lat=float(location.get("latitude", 0.0)), lon=float(location.get("longitude", 0.0)) )
        event.enrichment = {"severity": self._severity_map.get(alert_type, "medium"), "alert_type": alert_type}  # type: ignore[attr-defined]
        return event

    def severity_from_alert_type(self, alert_type: str) -> str:
        return self._severity_map.get(alert_type, "medium")
