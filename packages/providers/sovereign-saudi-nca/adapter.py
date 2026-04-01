"""Saudi NCA sovereign cybersecurity advisories adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier

from .config import SaudiNCAConfig
from .normalizer import SaudiNCANormalizer


class SaudiNCAAdapter(ProviderAdapter):
    def __init__(self, config: SaudiNCAConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or SaudiNCAConfig()
        self.normalizer = SaudiNCANormalizer()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _incoming_dir(self) -> Path:
        return Path(self.config.incoming_dir)

    def _has_api_credentials(self) -> bool:
        key = os.getenv("S3M_NCA_API_KEY") or os.getenv("NCA_API_KEY")
        cert = os.getenv("S3M_NCA_CLIENT_CERT") or os.getenv("NCA_CLIENT_CERT")
        return bool(key or cert)

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="sovereign-saudi-nca",
            name="Saudi NCA Sovereign Cyber Authority",
            category=ProviderCategory.SOVEREIGN_REGIONAL,
            tier=ProviderTier.GOVERNMENT,
            base_url=self.config.api_url,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            supported_schemas=["NormalizedThreatIndicator"],
            required_env_vars=[],
            optional_env_vars=["NCA_API_KEY", "NCA_CLIENT_CERT"],
            description="Saudi National Cybersecurity Authority advisories and compliance controls.",
            docs_url="https://nca.gov.sa",
            airgap_capable=True,
            enabled=True,
            tags=["saudi", "nca", "cyber", "sovereign", "government"],
        )

    def validate_credentials(self) -> bool:
        if self._has_api_credentials() and self.mode != "airgapped":
            return True
        if self._incoming_dir().exists():
            return True
        return (self._fixture_dir() / "fixtures" / "advisories.json").exists()

    def get_advisories(self, severity: str | None = None, days_back: int = 30) -> dict[str, Any]:
        payload = self._load_fixture_json("advisories.json")
        advisories = payload.get("advisories", [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(days_back))
        filtered: list[dict[str, Any]] = []
        for adv in advisories:
            published = datetime.fromisoformat(str(adv.get("published_date")).replace("Z", "+00:00"))
            if published < cutoff:
                continue
            if severity and str(adv.get("severity", "")).lower() != severity.lower():
                continue
            filtered.append(adv)
        return {"advisories": filtered, "count": len(filtered), "classification": "SAUDI_GOVERNMENT"}

    def get_vulnerability_alerts(self, active_only: bool = True) -> dict[str, Any]:
        payload = self._load_fixture_json("vulnerability_alerts.json")
        vulns = payload.get("vulnerabilities", [])
        if active_only:
            vulns = [v for v in vulns if v.get("active", True)]
        return {"vulnerabilities": vulns, "count": len(vulns)}

    def get_compliance_status(self, framework: str = "CCC") -> dict[str, Any]:
        payload = self._load_fixture_json("compliance_ccc.json")
        payload["framework"] = framework
        return payload

    def get_ioc_feed(self, ioc_type: str | None = None, confidence: str = "high") -> dict[str, Any]:
        payload = self._load_fixture_json("ioc_feed.json")
        iocs = payload.get("iocs", [])
        if ioc_type:
            iocs = [i for i in iocs if str(i.get("type", "")).lower() == ioc_type.lower()]
        iocs = [i for i in iocs if str(i.get("confidence", "")).lower() == confidence.lower()]
        return {"iocs": iocs, "count": len(iocs)}

    def ingest_from_directory(self) -> dict[str, Any]:
        incoming = self._incoming_dir()
        if not incoming.exists():
            return {"advisories": [], "count": 0}
        advisories: list[dict[str, Any]] = []
        for file_path in sorted(incoming.glob("*.json")):
            try:
                advisories.extend(json.loads(file_path.read_text(encoding="utf-8")).get("advisories", []))
            except Exception:
                continue
        return {"advisories": advisories, "count": len(advisories)}

    def feed_to_soc(self, advisories: list[dict[str, Any]]) -> dict[str, Any]:
        # Tactical context: critical sovereign advisories must trigger immediate SOC escalation.
        soc_alerts = []
        cti_iocs = []
        for advisory in advisories:
            if str(advisory.get("severity", "")).lower() == "critical":
                soc_alerts.append({
                    "alert_type": "SOVEREIGN_NCA_CRITICAL",
                    "severity": "critical",
                    "title": advisory.get("title_en") or advisory.get("title_ar"),
                    "advisory_id": advisory.get("advisory_id"),
                })
            cti_iocs.extend(advisory.get("iocs", []))
        return {
            "soc_alerts": soc_alerts,
            "critical_count": len(soc_alerts),
            "cti_iocs": cti_iocs,
            "cti_count": len(cti_iocs),
        }

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        endpoint = params.get("endpoint", "advisories")
        if endpoint == "advisories":
            return self.get_advisories(severity=params.get("severity"), days_back=int(params.get("days_back", 30)))
        if endpoint == "vulnerabilities":
            return self.get_vulnerability_alerts(active_only=bool(params.get("active_only", True)))
        if endpoint == "compliance":
            return self.get_compliance_status(framework=str(params.get("framework", "CCC")))
        if endpoint == "iocs":
            return self.get_ioc_feed(ioc_type=params.get("ioc_type"), confidence=str(params.get("confidence", "high")))
        if endpoint == "ingest":
            return self.ingest_from_directory()
        return self.get_advisories()

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        out: list[Any] = []
        for advisory in raw_data.get("advisories", []):
            out.extend(self.normalizer.normalize_advisory(advisory))
        for vuln in raw_data.get("vulnerabilities", []):
            out.append(self.normalizer.normalize_vulnerability(vuln))
        for ioc in raw_data.get("iocs", []):
            out.append(self.normalizer.normalize_ioc(ioc))
        return out

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.validate_credentials() else "degraded",
            "detail": {
                "mode": self.mode,
                "frameworks": self.config.compliance_frameworks,
                "critical_sectors": self.config.saudi_critical_sectors,
            },
        }
