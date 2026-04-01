"""CTI enrichment chain composing five providers for SOC triage."""

from __future__ import annotations

from collections import defaultdict
import time
from typing import Any

from packages.providers.registry import ProviderRegistry
from packages.schemas.threat_intel.models import NormalizedThreatIndicator, merge_indicators, severity_max, severity_min, severity_rank


class CTIEnrichmentChain:
    def __init__(self, mode: str = "airgapped") -> None:
        self.registry = ProviderRegistry()
        self.registry.register_default_cti_providers(mode=mode)
        self.providers = self.registry.as_dict()
        self.enrichment_order = ["cyber-misp", "cyber-opencti", "cyber-greynoise", "cyber-abuseipdb", "cyber-virustotal"]
        self._stats_total = 0
        self._stats_provider_calls: dict[str, int] = defaultdict(int)
        self._stats_total_time_ms = 0.0
        self._cache: dict[tuple[str, str], NormalizedThreatIndicator] = {}
        self._cache_hits = 0

    def _base(self, indicator_type: str, value: str) -> NormalizedThreatIndicator:
        return NormalizedThreatIndicator(indicator_type=indicator_type, value=value, threat_type="unknown", severity="low", source_feed="CTIEnrichmentChain", tags=["cti:base"], provenance={"provider_id": "cti-chain"}, confidence=0.3)

    def _lookup_misp(self, indicator_type: str, value: str) -> NormalizedThreatIndicator | None:
        p = self.providers["cyber-misp"]
        self._stats_provider_calls["cyber-misp"] += 1
        attrs = p.fetch({"endpoint": "attributes", "limit": 500}).get("attributes", [])
        events = p.fetch({"endpoint": "events", "limit": 50}).get("events", [])
        em = {str(e.get("id")): e for e in events}
        for a in attrs:
            if str(a.get("value", "")).strip().lower() == value.lower():
                return p.normalizer.normalize_attribute(a, event_context=em.get(str(a.get("event_id", "")), {}))
        return None

    def _lookup_opencti(self, indicator_type: str, value: str) -> NormalizedThreatIndicator | None:
        p = self.providers["cyber-opencti"]
        self._stats_provider_calls["cyber-opencti"] += 1
        nodes = p.fetch({"endpoint": "indicators", "limit": 100}).get("indicators", [])
        for n in nodes:
            ind = p.normalizer.normalize_indicator(n)
            if ind.indicator_type == indicator_type and ind.value.lower() == value.lower():
                return ind
        return None

    def _lookup_greynoise(self, indicator_type: str, value: str) -> NormalizedThreatIndicator | None:
        if indicator_type != "ip":
            return None
        p = self.providers["cyber-greynoise"]
        self._stats_provider_calls["cyber-greynoise"] += 1
        return p.normalize(p.check_ip(value))

    def _lookup_abuseipdb(self, indicator_type: str, value: str) -> NormalizedThreatIndicator | None:
        if indicator_type != "ip":
            return None
        p = self.providers["cyber-abuseipdb"]
        self._stats_provider_calls["cyber-abuseipdb"] += 1
        return p.normalize(p.check_ip(value))

    def _lookup_virustotal(self, indicator_type: str, value: str) -> NormalizedThreatIndicator | None:
        p = self.providers["cyber-virustotal"]
        self._stats_provider_calls["cyber-virustotal"] += 1
        t = "hash" if indicator_type.startswith("hash") else indicator_type
        return p.normalize(p.fetch({"type": t, "value": value}))

    def enrich_indicator(self, indicator_type: str, value: str) -> NormalizedThreatIndicator:
        key = (indicator_type, value)
        if key in self._cache:
            self._cache_hits += 1
            return self._cache[key]

        start = time.perf_counter()
        result = self._base(indicator_type, value)

        misp = self._lookup_misp(indicator_type, value)
        if misp:
            result = merge_indicators(result, misp)
        opencti = self._lookup_opencti(indicator_type, value)
        if opencti:
            result = merge_indicators(result, opencti)
        gn = self._lookup_greynoise(indicator_type, value)
        if gn:
            result = merge_indicators(result, gn)
            if gn.threat_type in {"scanner_benign", "known_service"}:
                result.severity = severity_min(result.severity, "low")
                result.tags.append("noise")
            elif gn.threat_type == "potentially_targeted":
                result.severity = severity_max(result.severity, "high")
                result.tags.append("targeted")
        abuse = self._lookup_abuseipdb(indicator_type, value)
        if abuse:
            result = merge_indicators(result, abuse)
        vt = self._lookup_virustotal(indicator_type, value)
        if vt:
            result = merge_indicators(result, vt)

        candidates = [x for x in [misp, opencti, gn, abuse, vt] if x is not None]
        if candidates:
            result.severity = max([result.severity] + [c.severity for c in candidates], key=severity_rank)
            if gn and gn.threat_type in {"scanner_benign", "known_service"}:
                result.severity = severity_min(result.severity, "low")
            if gn and gn.threat_type == "potentially_targeted":
                result.severity = severity_max(result.severity, "high")

            weighted_sum, weight_total = 0.0, 0.0
            for c, w in [(misp, 1.0), (opencti, 1.0), (gn, 1.0), (abuse, 1.5), (vt, 2.0)]:
                if c is None:
                    continue
                weighted_sum += c.reputation_score * w
                weight_total += w
            if weight_total > 0:
                result.reputation_score = weighted_sum / weight_total
            result.tags = sorted(set(result.tags + [t for c in candidates for t in c.tags]))
            result.mitre_techniques = sorted(set(result.mitre_techniques + [m for c in candidates for m in c.mitre_techniques]))

        self._stats_total += 1
        self._stats_total_time_ms += (time.perf_counter() - start) * 1000.0
        self._cache[key] = result
        return result

    def enrich_batch(self, indicators: list[tuple[str, str]]) -> list[NormalizedThreatIndicator]:
        return [self.enrich_indicator(t, v) for t, v in indicators]

    def enrich_from_phase13_alert(self, threat_event: dict[str, Any]) -> NormalizedThreatIndicator:
        observables: list[tuple[str, str]] = []
        for o in threat_event.get("observables", []):
            if isinstance(o, dict) and o.get("value"):
                typ = str(o.get("type", "ip")).lower()
                if typ in {"ip", "ip_address"}: typ = "ip"
                elif typ == "domain": typ = "domain"
                elif typ in {"sha256", "hash_sha256"}: typ = "hash_sha256"
                observables.append((typ, str(o["value"])))
        raw = threat_event.get("raw_data", {})
        for key in ("source_ip", "src_ip", "ip"):
            if key in raw:
                observables.append(("ip", str(raw[key])))
        if "domain" in raw:
            observables.append(("domain", str(raw["domain"])))
        if not observables:
            return self._base("ip", "0.0.0.0")
        enriched = self.enrich_batch(observables)
        return max(enriched, key=lambda i: severity_rank(i.severity))

    def get_enrichment_stats(self) -> dict[str, Any]:
        avg = self._stats_total_time_ms / self._stats_total if self._stats_total else 0.0
        total = self._stats_total + self._cache_hits
        cache_rate = (self._cache_hits / total) if total else 0.0
        return {"total_enriched": self._stats_total, "by_provider": dict(self._stats_provider_calls), "avg_enrichment_time_ms": round(avg, 3), "cache_hit_rate": round(cache_rate, 3)}

    def health_check(self) -> dict[str, Any]:
        detail, status = {}, "ok"
        for pid in self.enrichment_order:
            out = self.providers[pid].health_check()
            detail[pid] = out
            if out.get("status") != "ok":
                status = "degraded"
        return {"status": status, "detail": detail}
