"""Composable enrichment chain for normalized integration records."""

from __future__ import annotations

from typing import Any, Callable, Iterable


class ChainedEnrichmentPipeline:
    """Apply a deterministic sequence of enrichment functions."""

    def __init__(self, enrichers: Iterable[Callable[[Any], Any]]) -> None:
        self.enrichers = list(enrichers)

    def run(self, record: Any) -> Any:
        enriched = record
        for enricher in self.enrichers:
            enriched = enricher(enriched)
        return enriched
