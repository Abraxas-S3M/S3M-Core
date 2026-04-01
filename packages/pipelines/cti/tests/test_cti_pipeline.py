from __future__ import annotations

from packages.pipelines.cti import CTIDeduplicator, CTIEnrichmentChain, IOCIngestionWorker
from packages.schemas.threat_intel.models import NormalizedThreatIndicator


def test_enrichment_chain_order(monkeypatch):
    chain = CTIEnrichmentChain(mode="airgapped")
    calls = []

    def wrap(name, fn):
        def inner(*args, **kwargs):
            calls.append(name)
            return fn(*args, **kwargs)
        return inner

    monkeypatch.setattr(chain, "_lookup_misp", wrap("misp", chain._lookup_misp))
    monkeypatch.setattr(chain, "_lookup_opencti", wrap("opencti", chain._lookup_opencti))
    monkeypatch.setattr(chain, "_lookup_greynoise", wrap("greynoise", chain._lookup_greynoise))
    monkeypatch.setattr(chain, "_lookup_abuseipdb", wrap("abuseipdb", chain._lookup_abuseipdb))
    monkeypatch.setattr(chain, "_lookup_virustotal", wrap("virustotal", chain._lookup_virustotal))

    _ = chain.enrich_indicator("ip", "203.0.113.10")
    assert calls.index("greynoise") < calls.index("abuseipdb")
    assert calls.index("greynoise") < calls.index("virustotal")


def test_noise_downgrades_severity(monkeypatch):
    chain = CTIEnrichmentChain(mode="airgapped")
    monkeypatch.setattr(chain.providers["cyber-greynoise"], "check_ip", lambda ip: chain.providers["cyber-greynoise"]._load_fixture_json("ip_noise_benign.json"))
    out = chain.enrich_indicator("ip", "203.0.113.10")
    assert out.severity in {"info", "low"}


def test_targeted_upgrades_severity(monkeypatch):
    chain = CTIEnrichmentChain(mode="airgapped")
    monkeypatch.setattr(chain.providers["cyber-greynoise"], "check_ip", lambda ip: chain.providers["cyber-greynoise"]._load_fixture_json("ip_targeted.json"))
    out = chain.enrich_indicator("ip", "203.0.113.10")
    assert out.severity in {"high", "critical"}


def test_reputation_merge():
    chain = CTIEnrichmentChain(mode="airgapped")
    out = chain.enrich_indicator("ip", "45.155.205.233")
    assert 0 <= out.reputation_score <= 100


def test_mitre_techniques_merged():
    chain = CTIEnrichmentChain(mode="airgapped")
    out = chain.enrich_indicator("ip", "203.0.113.10")
    assert len(out.mitre_techniques) >= 1


def test_deduplication():
    d = CTIDeduplicator()
    a = NormalizedThreatIndicator(indicator_type="ip", value="1.2.3.4", tags=["a"], mitre_techniques=["T1566"], confidence=0.7, reputation_score=40)
    b = NormalizedThreatIndicator(indicator_type="ip", value="1.2.3.4", tags=["b"], mitre_techniques=["T1059"], confidence=0.8, reputation_score=60)
    out = d.deduplicate([a, b])
    assert len(out) == 1
    assert set(out[0].tags) >= {"a", "b"}


def test_ioc_ingestion_counts():
    w = IOCIngestionWorker(mode="airgapped")
    stats = w.ingest_latest(days_back=7)
    assert stats["misp_count"] >= 1
    assert stats["opencti_count"] >= 1
    assert stats["total_unique"] >= 1


def test_feed_to_threat_detection():
    w = IOCIngestionWorker(mode="airgapped")
    indicators = [NormalizedThreatIndicator(indicator_type="ip", value="203.0.113.10", severity="high", source_feed="MISP")]
    events = w.feed_to_threat_detection(indicators)
    assert len(events) == 1
    assert events[0].category.value == "CYBER"


def test_enrichment_stats():
    chain = CTIEnrichmentChain(mode="airgapped")
    _ = chain.enrich_indicator("ip", "203.0.113.10")
    stats = chain.get_enrichment_stats()
    assert "total_enriched" in stats
    assert "by_provider" in stats
    assert "avg_enrichment_time_ms" in stats
