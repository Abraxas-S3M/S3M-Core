"""Normalize AbuseIPDB responses to threat indicators."""

from __future__ import annotations

from typing import Any

from packages.schemas.threat_intel.models import NormalizedThreatIndicator
from .config import AbuseIPDBConfig


class AbuseIPDBNormalizer:
    def __init__(self, config: AbuseIPDBConfig | None = None) -> None:
        self.config = config or AbuseIPDBConfig()

    def _severity(self, score: int) -> str:
        if score >= 80:
            return "critical"
        if score >= 50:
            return "high"
        if score >= 20:
            return "medium"
        return "low"

    def map_abuse_categories(self, category_ids: list[int]) -> list[str]:
        return [self.config.abuse_category_names.get(int(cid), f"Unknown-{cid}") for cid in category_ids]

    def _threat_type(self, category_ids: list[int]) -> str:
        ids = set(int(x) for x in category_ids)
        if 18 in ids or 22 in ids or 5 in ids:
            return "brute_force"
        if 14 in ids:
            return "port_scan"
        if 4 in ids:
            return "ddos"
        if 21 in ids:
            return "web_attack"
        if 20 in ids:
            return "malware"
        if 23 in ids or 19 in ids:
            return "botnet"
        return "suspicious"

    def normalize_ip_check(self, data: dict[str, Any]) -> NormalizedThreatIndicator:
        reports = data.get("reports") or []
        category_ids: list[int] = []
        for r in reports:
            category_ids.extend([int(v) for v in r.get("categories", [])])
        mapped = self.map_abuse_categories(category_ids)
        first_seen = min((r.get("reportedAt") for r in reports if r.get("reportedAt")), default=None) if reports else None

        return NormalizedThreatIndicator(
            indicator_type="ip",
            value=str(data.get("ipAddress", "0.0.0.0")),
            threat_type=self._threat_type(category_ids),
            severity=self._severity(int(data.get("abuseConfidenceScore", 0) or 0)),
            first_seen=first_seen,
            last_seen=data.get("lastReportedAt"),
            reputation_score=float(data.get("abuseConfidenceScore", 0) or 0),
            source_feed="AbuseIPDB",
            tags=[
                f"country:{data.get('countryCode', 'unknown')}",
                f"isp:{data.get('isp', 'unknown')}",
                f"usage:{data.get('usageType', 'unknown')}",
                *[f"abuse:{name}" for name in mapped],
            ],
            provenance={"provider_id": "cyber-abuseipdb", "total_reports": data.get("totalReports", 0)},
            confidence=min(1.0, max(0.0, float(data.get("abuseConfidenceScore", 0)) / 100.0)),
        )

    def normalize_blacklist(self, entries: list[dict[str, Any]]) -> list[NormalizedThreatIndicator]:
        out: list[NormalizedThreatIndicator] = []
        for e in entries:
            out.append(NormalizedThreatIndicator(
                indicator_type="ip",
                value=str(e.get("ipAddress") or e.get("ip") or "0.0.0.0"),
                threat_type="blacklisted_ip",
                severity=self._severity(int(e.get("abuseConfidenceScore", 0) or 0)),
                first_seen=e.get("firstReportedAt") or e.get("lastReportedAt"),
                last_seen=e.get("lastReportedAt"),
                reputation_score=float(e.get("abuseConfidenceScore", 0) or 0),
                source_feed="AbuseIPDB",
                tags=[f"country:{e.get('countryCode', 'unknown')}", "abuse:blacklist"],
                provenance={"provider_id": "cyber-abuseipdb", "entry_type": "blacklist"},
                confidence=0.9,
            ))
        return out
