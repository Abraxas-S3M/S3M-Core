"""Normalize Recorded Future intelligence entities into threat indicators."""

from __future__ import annotations

from typing import Any

from packages.schemas.threat_intel.models import NormalizedThreatIndicator

from .config import RecordedFutureConfig


class RecordedFutureNormalizer:
    def __init__(self, config: RecordedFutureConfig | None = None) -> None:
        self.config = config or RecordedFutureConfig()

    def _severity(self, risk_score: int) -> str:
        if risk_score >= self.config.risk_thresholds["critical"]:
            return "critical"
        if risk_score >= self.config.risk_thresholds["high"]:
            return "high"
        if risk_score >= self.config.risk_thresholds["medium"]:
            return "medium"
        return "low"

    def _threat_type(self, rules: list[str]) -> str:
        text = " ".join(rules).lower()
        if "c2" in text:
            return "malware_c2"
        if "dark web" in text:
            return "dark_web_exposure"
        if "apt" in text:
            return "apt_association"
        return "suspicious"

    def normalize_entity(self, entity: dict[str, Any]) -> NormalizedThreatIndicator:
        risk_score = int(entity.get("risk_score", 0))
        rules = [str(x) for x in entity.get("risk_rules", [])]
        sightings = int(entity.get("sightings", 0))
        threat_lists = [str(x) for x in entity.get("threat_lists", [])]
        mitre = [str(x) for x in entity.get("mitre_techniques", [])]

        return NormalizedThreatIndicator(
            indicator_type=str(entity.get("entity_type", "ip")),
            value=str(entity.get("value", "")),
            threat_type=self._threat_type(rules),
            severity=self._severity(risk_score),
            reputation_score=float(risk_score),
            source_feed="Recorded Future",
            mitre_techniques=mitre,
            tags=[*rules, f"sightings:{sightings}", *[f"list:{t}" for t in threat_lists]],
            provenance={"provider_id": "cyber-recordedfuture", "risk_score": risk_score},
            confidence=0.90,
            enrichment={
                "risk_rules": rules,
                "sightings": sightings,
                "threat_lists": threat_lists,
            },
        )

    def normalize_threat_actor(self, actor: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(actor.get("name", "")),
            "aliases": list(actor.get("aliases", [])),
            "targets": list(actor.get("targets", [])),
            "ttps": list(actor.get("ttps", [])),
            "risk_score": int(actor.get("risk_score", 0)),
        }
