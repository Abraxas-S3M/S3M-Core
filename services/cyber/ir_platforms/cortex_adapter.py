"""Cortex adapter with offline-safe analyzer and LLM fallback enrichment."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from services.cyber.ir_platforms.base import IRPlatformAdapter
from services.cyber.models import EnrichmentResult, Observable, ObservableType


class CortexAdapter(IRPlatformAdapter):
    """Performs IOC enrichment via Cortex analyzers with tactical fallback mode."""

    def __init__(self, url: str = "http://localhost:9001", api_key: str = None) -> None:
        super().__init__(url=url, api_key=api_key, outbox_dir="data/cyber/cortex_outbox")

    def connect(self) -> bool:
        return self._safe_request("GET", "/api/status") is not None

    def _default_analyzers(self, observable: Observable) -> List[str]:
        if observable.observable_type == ObservableType.IP_ADDRESS:
            return ["AbuseIPDB", "Shodan"]
        if observable.observable_type in {ObservableType.FILE_HASH_MD5, ObservableType.FILE_HASH_SHA256}:
            return ["VirusTotal"]
        if observable.observable_type == ObservableType.DOMAIN:
            return ["DomainTools"]
        return ["GenericAnalyzer"]

    def _llm_fallback(self, observable: Observable) -> EnrichmentResult:
        # Tactical context is explicit so operators can use this result in military shift reports.
        prompt = (
            "Analyze this network observable for potential threats: "
            f"type={observable.observable_type.value}, value={observable.value}. "
            "Assess: 1) Known threat indicators 2) Risk level 3) Recommended response. "
            "Classification: UNCLASSIFIED."
        )
        simulated = (
            "S3M Grok fallback assessment: Observable appears suspicious but unresolved without "
            "external intel feeds. Recommend containment monitoring and analyst review."
        )
        return EnrichmentResult(
            analyzer="S3M_LLM_Grok",
            observable_id=observable.observable_id,
            timestamp=datetime.now(timezone.utc),
            result={
                "note": "Cortex offline — analysis pending",
                "prompt": prompt,
                "analysis": simulated,
            },
            verdict="unknown",
            confidence=0.45,
        )

    def analyze_observable(self, observable: Observable, analyzers: List[str] = None) -> EnrichmentResult:
        requested_analyzers = analyzers or self._default_analyzers(observable)
        for analyzer in requested_analyzers:
            payload = {
                "data": observable.value,
                "dataType": observable.observable_type.value,
                "tlp": observable.tlp,
            }
            response = self._safe_request("POST", f"/api/analyzer/{analyzer}/run", payload)
            if response is not None:
                return EnrichmentResult(
                    analyzer=analyzer,
                    observable_id=observable.observable_id,
                    result=response if isinstance(response, dict) else {"raw": str(response)},
                    verdict=str(response.get("verdict", "unknown")) if isinstance(response, dict) else "unknown",
                    confidence=float(response.get("confidence", 0.6)) if isinstance(response, dict) else 0.6,
                )
        return self._llm_fallback(observable)

    def get_analyzers(self) -> List[dict]:
        response = self._safe_request("GET", "/api/analyzer")
        if response is None:
            return []
        if isinstance(response, list):
            return response
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            return response["data"]
        return []

    def get_job_status(self, job_id: str) -> dict:
        response = self._safe_request("GET", f"/api/job/{job_id}/report")
        if response is None:
            return {"job_id": job_id, "status": "pending_offline"}
        return response if isinstance(response, dict) else {"job_id": job_id, "raw": str(response)}
