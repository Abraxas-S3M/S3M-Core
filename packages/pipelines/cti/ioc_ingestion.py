"""Bulk IOC ingestion pipeline bridging CTI sources into ThreatManager."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from packages.pipelines.cti.dedup import CTIDeduplicator
from packages.providers.registry import ProviderRegistry
from packages.schemas.threat_intel.models import NormalizedThreatIndicator
from src.threat_detection.threat_manager import ThreatManager


class IOCIngestionWorker:
    def __init__(self, mode: str = "airgapped") -> None:
        self.registry = ProviderRegistry()
        self.registry.register_default_cti_providers(mode=mode)
        self.misp = self.registry.get("cyber-misp")
        self.opencti = self.registry.get("cyber-opencti")
        self.dedup = CTIDeduplicator()
        self.threat_manager = ThreatManager(max_entries=20_000)

    def ingest_latest(self, days_back: int = 7) -> dict[str, int]:
        misp_raw = self.misp.fetch({"endpoint": "attributes", "days_back": days_back, "limit": 500})
        events = self.misp.fetch({"endpoint": "events", "days_back": max(30, days_back), "limit": 50}).get("events", [])
        em = {str(e.get("id")): e for e in events}
        misp_ind = self.misp.normalizer.normalize_batch(misp_raw.get("attributes", []), event_map=em)

        oc_raw = self.opencti.fetch({"endpoint": "indicators", "days_back": days_back, "limit": 100})
        oc_ind = self.opencti.normalizer.normalize_batch(oc_raw.get("indicators", []))

        merged = misp_ind + oc_ind
        deduped = self.dedup.deduplicate(merged)

        out_dir = Path("data/integrations/cti-merged")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"cti_merged_{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        out_path.write_text(json.dumps([i.__dict__ for i in deduped], indent=2), encoding="utf-8")

        return {
            "misp_count": len(misp_ind),
            "opencti_count": len(oc_ind),
            "total_unique": len(deduped),
            "deduplicated": len(merged) - len(deduped),
        }

    def feed_to_threat_detection(self, indicators: list[NormalizedThreatIndicator]):
        out = []
        for i in indicators:
            level = i.severity.upper()
            if level == "INFO":
                level = "LOW"
            e = self.threat_manager.ingest_manual(
                title=f"External CTI IOC matched: {i.indicator_type} {i.value}",
                description=f"IOC enriched from {i.source_feed}; threat_type={i.threat_type}; reputation={i.reputation_score:.1f}.",
                level=level,
                category="CYBER",
            )
            out.append(e)
        return out
