"""Normalize GreyNoise noise/riot context for SOC alert triage."""

from __future__ import annotations

from typing import Any

from packages.schemas.threat_intel.models import NormalizedThreatIndicator


class GreyNoiseNormalizer:
    def normalize_ip(self, data: dict[str, Any]) -> NormalizedThreatIndicator:
        noise = bool(data.get("noise", False))
        riot = bool(data.get("riot", False))
        classification = str(data.get("classification", "unknown")).lower()

        if riot:
            threat_type, severity, reputation = "known_service", "info", 5.0
        elif noise and classification == "malicious":
            threat_type, severity, reputation = "scanner_malicious", "medium", 60.0
        elif noise and classification == "benign":
            threat_type, severity, reputation = "scanner_benign", "info", 20.0
        else:
            threat_type, severity, reputation = "potentially_targeted", "high", 80.0

        tags = [
            f"classification:{classification}",
            f"scanner:{data.get('name', 'unknown')}",
            f"noise:{str(noise).lower()}",
            f"riot:{str(riot).lower()}",
        ]

        return NormalizedThreatIndicator(
            indicator_type="ip",
            value=str(data.get("ip", "0.0.0.0")),
            threat_type=threat_type,
            severity=severity,
            first_seen=data.get("last_seen"),
            last_seen=data.get("last_seen"),
            reputation_score=reputation,
            source_feed="GreyNoise",
            tags=tags,
            provenance={"provider_id": "cyber-greynoise", "link": data.get("link")},
            confidence=0.85,
        )
