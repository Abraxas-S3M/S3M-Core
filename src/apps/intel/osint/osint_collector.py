"""OSINT collection orchestrator for Phase 19 intelligence operations."""

from __future__ import annotations

from datetime import datetime, timezone

from src.apps.intel.models import OSINTItem
from src.apps.intel.osint.analyzer import OSINTAnalyzer
from src.apps.intel.osint.ingester import OSINTIngester
from src.apps.intel.osint.source_manager import SourceManager


class OSINTCollector:
    """Coordinate source registration, ingestion, and enrichment pipeline."""

    def __init__(self) -> None:
        self.source_manager = SourceManager()
        self.ingester = OSINTIngester()
        self.analyzer = OSINTAnalyzer()
        self._items: list[OSINTItem] = []
        self._last_cross_refs: list[dict] = []

    def collect(self) -> dict:
        for source in self.source_manager.get_sources(active_only=True):
            self.ingester.set_source_reliability(source.source_id, source.reliability)

        result = self.ingester.ingest_directory()
        new_items = self.ingester.items[len(self._items) :]
        analyzed = self.analyzer.analyze_batch(new_items)
        self._items.extend(analyzed)
        self._last_cross_refs = self.analyzer.cross_reference(self._items)

        return {
            "items_collected": len(analyzed),
            "high_relevance": len([item for item in analyzed if item.relevance_score >= 0.7]),
            "cross_referenced": len(self._last_cross_refs),
            "sources_used": sorted({item.source_id for item in analyzed}),
            "ingestion": result,
        }

    def get_items(
        self,
        region: str | None = None,
        topic: str | None = None,
        min_relevance: float = 0.0,
        since: datetime | str | None = None,
        limit: int = 100,
    ) -> list[OSINTItem]:
        values = list(self._items)
        if region:
            needle = region.strip().lower()
            values = [
                item
                for item in values
                if any(needle in reg.lower() for reg in item.regions)
            ]
        if topic:
            topic_needle = topic.strip().lower()
            values = [
                item
                for item in values
                if any(topic_needle in candidate.lower() for candidate in item.topics)
            ]
        values = [item for item in values if item.relevance_score >= min_relevance]
        if since:
            if isinstance(since, str):
                try:
                    since_dt = datetime.fromisoformat(since)
                except Exception:
                    since_dt = datetime.now(timezone.utc)
            else:
                since_dt = since
            values = [
                item
                for item in values
                if item.timestamp.astimezone(timezone.utc)
                >= since_dt.astimezone(timezone.utc)
            ]
        values.sort(key=lambda item: item.timestamp, reverse=True)
        return values[: max(1, int(limit))]

    def get_high_priority_items(self, threshold: float = 0.7) -> list[OSINTItem]:
        return [item for item in self._items if item.relevance_score >= threshold]

    def search(self, query: str) -> list[OSINTItem]:
        needle = query.strip().lower()
        if not needle:
            return []
        out: list[OSINTItem] = []
        for item in self._items:
            blob = " ".join(
                [
                    item.title,
                    item.content,
                    " ".join(str(ent.get("value", "")) for ent in item.entities),
                ]
            ).lower()
            if needle in blob:
                out.append(item)
        return out

    def get_collection_stats(self) -> dict:
        by_source: dict[str, int] = {}
        for item in self._items:
            by_source[item.source_id] = by_source.get(item.source_id, 0) + 1
        return {
            "total_items": len(self._items),
            "high_priority": len(self.get_high_priority_items()),
            "sources": by_source,
            "cross_references": len(self._last_cross_refs),
            "ingestion": self.ingester.get_ingestion_stats(),
            "source_stats": self.source_manager.get_source_stats(),
        }

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "watch_dir": self.ingester.watch_dir,
            "sources_active": len(self.source_manager.get_sources(active_only=True)),
            "items_cached": len(self._items),
            "cross_refs": len(self._last_cross_refs),
        }
