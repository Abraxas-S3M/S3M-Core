"""Normalize Janes equipment, ORBAT, and threat intelligence records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.common.base import Provenance
from packages.schemas.event_intel.models import NormalizedGlobalEvent


class JanesNormalizer:
    def normalize_equipment(self, equipment: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(equipment.get("name", "")),
            "type": str(equipment.get("type", "")),
            "manufacturer": str(equipment.get("manufacturer", "")),
            "country_of_origin": str(equipment.get("country_of_origin", "")),
            "specifications": dict(equipment.get("specifications", {})),
            "performance": dict(equipment.get("performance", {})),
            "operators": list(equipment.get("operators", [])),
            "phase17_asset_registry_link": True,
        }

    def normalize_orbat(self, orbat: dict[str, Any]) -> dict[str, Any]:
        return {
            "country_code": str(orbat.get("country_code", "SA")),
            "branches": list(orbat.get("branches", [])),
            "units": list(orbat.get("units", [])),
            "phase16_orbat_compatible": True,
        }

    def normalize_threat(self, assessment: dict[str, Any]) -> NormalizedGlobalEvent:
        return NormalizedGlobalEvent(
            event_type="threat_assessment",
            actors=list(assessment.get("actors", [])),
            country=str(assessment.get("country", "")),
            region=str(assessment.get("region", "middle-east")),
            source_count=int(assessment.get("source_count", 1)),
            sentiment_score=float(assessment.get("sentiment_score", -0.4)),
            tags=["janes", "defense_intel", "premium"],
            provenance=Provenance(
                provider_id="intel-janes",
                provider_name="Janes",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(assessment.get("id", "unknown")),
                confidence=0.95,
                classification="UNCLASSIFIED",
            ),
        )

    def normalize_news(self, article: dict[str, Any]) -> NormalizedGlobalEvent:
        return NormalizedGlobalEvent(
            event_type="defense_analysis",
            actors=[str(article.get("publisher", "Janes"))],
            country=str(article.get("country", "")),
            region=str(article.get("region", "middle-east")),
            source_count=1,
            sentiment_score=float(article.get("sentiment_score", -0.2)),
            tags=["janes", "defense_news", "premium"],
            provenance=Provenance(
                provider_id="intel-janes",
                provider_name="Janes",
                fetched_at=datetime.now(timezone.utc),
                raw_id=str(article.get("id", "unknown")),
                confidence=0.92,
                classification="UNCLASSIFIED",
            ),
        )
