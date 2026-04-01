"""Deduplication for merged CTI indicators from multiple sources."""

from __future__ import annotations

from packages.schemas.threat_intel.models import NormalizedThreatIndicator, merge_indicators


class CTIDeduplicator:
    def deduplicate(self, indicators: list[NormalizedThreatIndicator]) -> list[NormalizedThreatIndicator]:
        by_key: dict[tuple[str, str], NormalizedThreatIndicator] = {}
        for indicator in indicators:
            key = (indicator.indicator_type, indicator.value)
            if key not in by_key:
                by_key[key] = indicator
                continue
            current = by_key[key]
            preferred = indicator if (indicator.confidence, indicator.reputation_score) > (current.confidence, current.reputation_score) else current
            secondary = current if preferred is indicator else indicator
            by_key[key] = merge_indicators(preferred, secondary)
        return list(by_key.values())
