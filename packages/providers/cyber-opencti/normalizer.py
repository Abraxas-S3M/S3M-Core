"""Normalize OpenCTI GraphQL records to unified threat indicators."""

from __future__ import annotations

import re
from typing import Any

from packages.schemas.threat_intel.models import NormalizedThreatIndicator


class OpenCTINormalizer:
    def parse_stix_pattern(self, pattern: str) -> tuple[str, str]:
        text = (pattern or "").strip()

        m = re.search(r"\[ipv[46]-addr:value\s*=\s*'([^']+)'\]", text)
        if m:
            return "ip", m.group(1)

        m = re.search(r"\[domain-name:value\s*=\s*'([^']+)'\]", text)
        if m:
            return "domain", m.group(1)

        m = re.search(r"\[url:value\s*=\s*'([^']+)'\]", text)
        if m:
            return "url", m.group(1)

        m = re.search(r"\[email-addr:value\s*=\s*'([^']+)'\]", text)
        if m:
            return "email", m.group(1)

        m = re.search(r"file:hashes\.'(MD5|SHA-1|SHA-256)'\s*=\s*'([^']+)'", text)
        if m:
            algo = m.group(1).upper()
            value = m.group(2)
            if algo == "MD5":
                return "hash_md5", value
            if algo == "SHA-1":
                return "hash_sha1", value
            return "hash_sha256", value

        return "unknown", text

    def _score_to_severity(self, score: int) -> str:
        if score >= 80:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    def normalize_indicator(self, node: dict[str, Any]) -> NormalizedThreatIndicator:
        indicator_type, value = self.parse_stix_pattern(str(node.get("pattern", "")))
        score = int(node.get("x_opencti_score") or 0)
        kill_chain = node.get("killChainPhases") or []
        techniques = [str(p.get("phase_name", "")).strip() for p in kill_chain if str(p.get("phase_name", "")).strip()]
        labels = [str(l.get("value", "")) for l in node.get("objectLabel", []) if str(l.get("value", "")).strip()]
        source = node.get("createdBy", {}).get("name") if isinstance(node.get("createdBy"), dict) else "OpenCTI"

        return NormalizedThreatIndicator(
            indicator_type=indicator_type,
            value=value,
            threat_type="opencti_indicator",
            severity=self._score_to_severity(score),
            first_seen=node.get("valid_from") or node.get("created_at"),
            last_seen=node.get("valid_until") or node.get("created_at"),
            mitre_techniques=sorted(set(techniques)),
            reputation_score=float(score),
            source_feed=source or "OpenCTI",
            tags=labels,
            provenance={"provider_id": "cyber-opencti", "opencti_id": node.get("id")},
            confidence=min(1.0, max(0.0, float(score) / 100.0)),
        )

    def normalize_threat_actor(self, node: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": node.get("name", ""),
            "aliases": list(node.get("aliases", [])),
            "motivation": node.get("primary_motivation", "unknown"),
            "sophistication": node.get("sophistication", "unknown"),
            "first_seen": node.get("first_seen"),
            "last_seen": node.get("last_seen"),
            "labels": [label.get("value") for label in node.get("objectLabel", []) if label.get("value")],
        }

    def normalize_batch(self, nodes: list[dict[str, Any]]) -> list[NormalizedThreatIndicator]:
        return [self.normalize_indicator(node) for node in nodes]
