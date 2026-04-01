"""Normalize VirusTotal lookups into tactical IOC reputation signals."""

from __future__ import annotations

from typing import Any

from packages.schemas.threat_intel.models import NormalizedThreatIndicator


class VirusTotalNormalizer:
    def __init__(self, malicious_threshold: int = 3) -> None:
        self.malicious_threshold = malicious_threshold

    def _map_vt_reputation(self, vt_reputation: int | float) -> float:
        score = 50.0 - (float(vt_reputation) / 2.0)
        return max(0.0, min(100.0, score))

    def compute_reputation_score(self, analysis_stats: dict[str, Any]) -> float:
        malicious = float(analysis_stats.get("malicious", 0) or 0)
        harmless = float(analysis_stats.get("harmless", 0) or 0)
        suspicious = float(analysis_stats.get("suspicious", 0) or 0)
        undetected = float(analysis_stats.get("undetected", 0) or 0)
        denom = malicious + harmless + suspicious + undetected + 1.0
        return max(0.0, min(100.0, 100.0 * malicious / denom))

    def compute_severity(self, malicious_count: int) -> str:
        if malicious_count >= 10:
            return "critical"
        if malicious_count >= 5:
            return "high"
        if malicious_count >= 1:
            return "medium"
        return "low"

    def _threat_type(self, scope: str, malicious_count: int, suspicious_count: int) -> str:
        if malicious_count > self.malicious_threshold:
            return f"malicious_{scope}"
        if malicious_count > 0 or suspicious_count > 0:
            return "suspicious"
        return "benign"

    def normalize_ip_report(self, report: dict[str, Any]) -> NormalizedThreatIndicator:
        data = report.get("data", {})
        attrs = data.get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})
        malicious = int(stats.get("malicious", 0) or 0)
        suspicious = int(stats.get("suspicious", 0) or 0)
        value = str(data.get("id") or attrs.get("ip") or "0.0.0.0")
        tags = [f"country:{attrs.get('country', 'unknown')}", f"as_owner:{attrs.get('as_owner', 'unknown')}" ]
        if isinstance(attrs.get("categories"), dict):
            tags.extend([f"category:{v}" for v in attrs["categories"].values()])
        return NormalizedThreatIndicator(
            indicator_type="ip", value=value,
            threat_type=self._threat_type("ip", malicious, suspicious),
            severity=self.compute_severity(malicious),
            reputation_score=self._map_vt_reputation(attrs.get("reputation", 0)),
            source_feed="VirusTotal", tags=tags,
            provenance={"provider_id": "cyber-virustotal", "analysis_stats": stats},
            confidence=0.8 if malicious > 0 else 0.5,
        )

    def normalize_domain_report(self, report: dict[str, Any]) -> NormalizedThreatIndicator:
        data = report.get("data", {})
        attrs = data.get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})
        malicious = int(stats.get("malicious", 0) or 0)
        suspicious = int(stats.get("suspicious", 0) or 0)
        domain = str(data.get("id") or attrs.get("domain") or "unknown")
        tags = [f"registrar:{attrs.get('registrar', 'unknown')}"]
        if isinstance(attrs.get("categories"), dict):
            tags.extend([f"category:{v}" for v in attrs["categories"].values()])
        return NormalizedThreatIndicator(
            indicator_type="domain", value=domain,
            threat_type=self._threat_type("domain", malicious, suspicious),
            severity=self.compute_severity(malicious),
            reputation_score=self._map_vt_reputation(attrs.get("reputation", 0)),
            source_feed="VirusTotal", tags=tags,
            provenance={"provider_id": "cyber-virustotal", "analysis_stats": stats},
            confidence=0.8 if malicious > 0 else 0.5,
        )

    def normalize_hash_report(self, report: dict[str, Any]) -> NormalizedThreatIndicator:
        data = report.get("data", {})
        attrs = data.get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})
        malicious = int(stats.get("malicious", 0) or 0)
        suspicious = int(stats.get("suspicious", 0) or 0)
        hash_value = str(data.get("id", ""))
        indicator_type = "hash_sha256" if len(hash_value) == 64 else "hash_md5"
        tags = [f"file_type:{attrs.get('type_description', 'unknown')}", f"file_size:{attrs.get('size', 0)}"]
        for verdict in attrs.get("sandbox_verdicts", []):
            tags.append(f"sandbox:{verdict}")
        return NormalizedThreatIndicator(
            indicator_type=indicator_type, value=hash_value,
            threat_type=self._threat_type("hash", malicious, suspicious),
            severity=self.compute_severity(malicious),
            reputation_score=self._map_vt_reputation(attrs.get("reputation", 0)),
            source_feed="VirusTotal", tags=tags,
            provenance={"provider_id": "cyber-virustotal", "analysis_stats": stats},
            confidence=0.9 if malicious > 0 else 0.5,
        )
