"""Normalization helpers for ACLED conflict and political events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.event_intel.models import NormalizedGlobalEvent


class ACLEDNormalizer:
    provider_id = "osint-acled"
    provider_name = "ACLED"
    _event_type_map = {
        "Battles": "conflict",
        "Explosions/Remote violence": "explosion",
        "Violence against civilians": "violence_civilians",
        "Protests": "protest",
        "Riots": "riot",
        "Strategic developments": "political",
    }

    type_map = dict(_event_type_map)

    sentiment_map = {
        "Battles": -0.8,
        "Explosions/Remote violence": -0.8,
        "Violence against civilians": -0.9,
        "Protests": -0.4,
        "Riots": -0.6,
        "Strategic developments": -0.2,
    }

    def _parse_timestamp(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.now(timezone.utc)

    def _as_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _confidence_from_geo_precision(self, geo_precision: int) -> float:
        if geo_precision == 1:
            return 0.95
        if geo_precision == 2:
            return 0.8
        return 0.6

    def compute_severity(self, event: dict[str, Any]) -> str:
        fatalities = self._as_int(event.get("fatalities"), 0)
        event_type = str(event.get("event_type", ""))
        if fatalities >= 20:
            return "critical"
        if fatalities >= 5:
            return "high"
        if fatalities >= 1:
            return "medium"
        if event_type == "Protests":
            return "low"
        return "medium"

    def normalize_event(self, event: dict[str, Any]) -> NormalizedGlobalEvent:
        event_type_raw = str(event.get("event_type", "Strategic developments"))
        mapped_type = self.type_map.get(event_type_raw, "political")
        fatalities = self._as_int(event.get("fatalities"), 0)
        geo_precision = self._as_int(event.get("geo_precision"), 3)
        actor1 = str(event.get("actor1", "")).strip()
        actor2 = str(event.get("actor2", "")).strip()
        actors = [name for name in [actor1, actor2] if name]
        severity = self.compute_severity(event)
        sentiment = self.sentiment_map.get(event_type_raw, -0.2)
        return NormalizedGlobalEvent(
            timestamp=self._parse_timestamp(str(event.get("event_date", ""))),
            event_type=mapped_type,
            actors=actors,
            fatalities=fatalities,
            country=str(event.get("country", "")).strip(),
            region=str(event.get("admin1", "")).strip(),
            source_count=1,
            sentiment_score=sentiment,
            language="en",
            geo_point=GeoPoint(
                lat=self._as_float(event.get("latitude"), 0.0),
                lon=self._as_float(event.get("longitude"), 0.0),
            ),
            tags=[
                "acled",
                event_type_raw,
                f"sub:{event.get('sub_event_type', '')}",
                f"severity:{severity}",
            ],
            raw_data_ref=str(event.get("source", "")),
            provenance=Provenance(
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(event.get("data_id", "")) or None,
                confidence=self._confidence_from_geo_precision(geo_precision),
                classification="UNCLASSIFIED",
            ),
        )

    def extract_conflict_actors(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        agg: dict[str, dict[str, int]] = defaultdict(lambda: {"event_count": 0, "fatalities": 0})
        for event in events:
            fatalities = self._as_int(event.get("fatalities"), 0)
            for key in ["actor1", "actor2"]:
                actor = str(event.get(key, "")).strip()
                if not actor:
                    continue
                agg[actor]["event_count"] += 1
                agg[actor]["fatalities"] += fatalities
        ranked = [
            {"actor": actor, "event_count": stats["event_count"], "fatalities_total": stats["fatalities"]}
            for actor, stats in agg.items()
        ]
        ranked.sort(key=lambda item: (item["fatalities_total"], item["event_count"]), reverse=True)
        return ranked
