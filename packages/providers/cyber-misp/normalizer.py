"""MISP response normalization into unified threat indicators."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

from packages.schemas.threat_intel.models import NormalizedThreatIndicator


class MISPNormalizer:
    ATTRIBUTE_TYPE_MAP = {
        "ip-src": "ip",
        "ip-dst": "ip",
        "domain": "domain",
        "hostname": "domain",
        "md5": "hash_md5",
        "sha1": "hash_sha1",
        "sha256": "hash_sha256",
        "url": "url",
        "email-src": "email",
        "vulnerability": "cve",
    }

    _ANALYSIS_CONFIDENCE = {0: 0.3, 1: 0.6, 2: 0.9}
    _EVENT_SEVERITY = {1: "critical", 2: "high", 3: "medium", 4: "low"}

    def normalize_attribute(self, attr: dict[str, Any], event_context: dict[str, Any] | None = None) -> NormalizedThreatIndicator:
        event_context = event_context or {}
        tags = list(attr.get("Tag", [])) + list(event_context.get("Tag", []))
        tag_names = [str(tag.get("name", "")) for tag in tags]

        indicator_type = self.ATTRIBUTE_TYPE_MAP.get(str(attr.get("type", "")).lower(), "unknown")
        value = str(attr.get("value", "")).strip()

        if any("malware" in tag.lower() for tag in tag_names):
            threat_type = "malware"
        elif any("apt" in tag.lower() for tag in tag_names):
            threat_type = "apt"
        elif any("mitre-attack-pattern" in tag.lower() for tag in tag_names):
            threat_type = "attack_pattern"
        else:
            threat_type = "unknown"

        timestamp = self._to_iso(attr.get("timestamp"))
        threat_level_id = int(event_context.get("threat_level_id", 3))
        analysis = int(event_context.get("analysis", 0))
        org = event_context.get("Org") if isinstance(event_context.get("Org"), dict) else {}

        return NormalizedThreatIndicator(
            indicator_type=indicator_type,
            value=value,
            threat_type=threat_type,
            severity=self._EVENT_SEVERITY.get(threat_level_id, "medium"),
            first_seen=timestamp,
            last_seen=timestamp,
            mitre_techniques=self.extract_mitre_from_tags(tags),
            reputation_score=0.0,
            source_feed=org.get("name") or "MISP",
            tlp=self.extract_tlp(tags),
            tags=tag_names,
            provenance={
                "provider_id": "cyber-misp",
                "event_id": event_context.get("id") or attr.get("event_id"),
                "confidence": self._ANALYSIS_CONFIDENCE.get(analysis, 0.3),
                "analysis": analysis,
            },
            confidence=self._ANALYSIS_CONFIDENCE.get(analysis, 0.3),
        )

    def normalize_batch(self, attributes: list[dict[str, Any]], event_map: dict[str, dict[str, Any]] | None = None) -> list[NormalizedThreatIndicator]:
        event_map = event_map or {}
        out: list[NormalizedThreatIndicator] = []
        for attr in attributes:
            event_id = str(attr.get("event_id", ""))
            out.append(self.normalize_attribute(attr, event_context=event_map.get(event_id, {})))
        return out

    def extract_mitre_from_tags(self, tags: list[dict[str, Any]]) -> list[str]:
        techniques: set[str] = set()
        for tag in tags:
            name = str(tag.get("name", ""))
            if "mitre-attack-pattern" not in name.lower():
                continue
            for candidate in re.findall(r"T\d{4}(?:\.\d{3})?", name):
                techniques.add(candidate)
        return sorted(techniques)

    def extract_tlp(self, tags: list[dict[str, Any]]) -> str:
        for tag in tags:
            name = str(tag.get("name", "")).lower()
            if "tlp:white" in name:
                return "WHITE"
            if "tlp:green" in name:
                return "GREEN"
            if "tlp:amber" in name:
                return "AMBER"
            if "tlp:red" in name:
                return "RED"
        return "AMBER"

    def _to_iso(self, ts: Any) -> str | None:
        if ts is None:
            return None
        try:
            return datetime.fromtimestamp(int(float(str(ts))), tz=UTC).isoformat()
        except Exception:
            return None
