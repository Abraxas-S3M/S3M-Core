"""Normalization for Saudi NCA advisories, vulnerabilities, and IOCs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.schemas.threat_intel.models import NormalizedThreatIndicator


class SaudiNCANormalizer:
    def normalize_advisory(self, advisory: dict[str, Any]) -> list[NormalizedThreatIndicator]:
        out: list[NormalizedThreatIndicator] = []
        iocs = advisory.get("iocs", [])
        for ioc in iocs:
            indicator = self.normalize_ioc(ioc)
            indicator.severity = str(advisory.get("severity", "medium")).lower()
            indicator.threat_type = "government_advisory"
            indicator.source_feed = "Saudi NCA"
            indicator.tlp = "AMBER"
            indicator.tags = sorted(set([
                *[str(s) for s in advisory.get("affected_sectors", [])],
                f"advisory:{advisory.get('advisory_id', '')}",
                "sovereign",
                "nca",
            ]))
            indicator.provenance = {
                "provider_id": "sovereign-saudi-nca",
                "advisory_id": advisory.get("advisory_id"),
            }
            indicator.confidence = 0.95
            out.append(indicator)
        return out

    def normalize_vulnerability(self, vuln: dict[str, Any]) -> NormalizedThreatIndicator:
        tags = ["sovereign", "nca", "cve"]
        if vuln.get("saudi_exploitation_confirmed"):
            tags.append("saudi_exploitation_confirmed")
        return NormalizedThreatIndicator(
            indicator_type="cve",
            value=str(vuln.get("cve_id", "")),
            threat_type="vulnerability",
            severity=str(vuln.get("severity", "medium")).lower(),
            first_seen=datetime.now(timezone.utc).isoformat(),
            last_seen=datetime.now(timezone.utc).isoformat(),
            source_feed="Saudi NCA",
            tlp="AMBER",
            tags=tags,
            provenance={"provider_id": "sovereign-saudi-nca"},
            confidence=0.95,
            reputation_score=90.0 if vuln.get("saudi_exploitation_confirmed") else 70.0,
        )

    def normalize_ioc(self, ioc: dict[str, Any]) -> NormalizedThreatIndicator:
        ioc_type = str(ioc.get("type", "ip")).lower()
        if ioc_type == "hash":
            ioc_type = "hash_sha256"
        return NormalizedThreatIndicator(
            indicator_type=ioc_type,
            value=str(ioc.get("value", "")),
            threat_type="ioc",
            severity="high",
            first_seen=ioc.get("first_seen") or datetime.now(timezone.utc).isoformat(),
            last_seen=ioc.get("last_seen") or datetime.now(timezone.utc).isoformat(),
            source_feed="Saudi NCA",
            tlp="AMBER",
            tags=["sovereign", "nca"],
            provenance={"provider_id": "sovereign-saudi-nca"},
            confidence=0.95,
            reputation_score=80.0,
        )
