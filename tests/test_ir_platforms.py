"""Tests for Layer 07 incident-response platform adapters and bridge."""

from __future__ import annotations

from services.cyber.ir_platforms import CortexAdapter, IRPlatformBridge, MISPAdapter, TheHiveAdapter
from services.cyber.models import CaseSeverity, IncidentCase, Observable, ObservableType


def _sample_case() -> IncidentCase:
    obs = Observable(
        observable_type=ObservableType.IP_ADDRESS,
        value="203.0.113.10",
        source_case_id="tmp-case",
    )
    return IncidentCase(
        title="Suspicious brute force",
        description="SSH brute force pattern observed",
        severity=CaseSeverity.HIGH,
        source_events=["evt-1"],
        observables=[obs.to_dict()],
    )


def test_thehive_adapter_offline_mode_saves_to_outbox():
    adapter = TheHiveAdapter(url="http://127.0.0.1:65531")
    result = adapter.create_alert(_sample_case())
    assert "error" in result
    assert adapter.get_outbox()


def test_cortex_adapter_llm_fallback_produces_expected_analyzer():
    adapter = CortexAdapter(url="http://127.0.0.1:65532")
    observable = Observable(
        observable_type=ObservableType.IP_ADDRESS,
        value="198.51.100.20",
        source_case_id="case-1",
    )
    result = adapter.analyze_observable(observable)
    assert result.analyzer == "S3M_LLM_Grok"
    assert result.verdict == "unknown"


def test_misp_adapter_offline_saves_to_outbox():
    adapter = MISPAdapter(url="http://127.0.0.1:65533")
    result = adapter.create_event(_sample_case())
    assert "error" in result
    assert adapter._read_outbox_files()


def test_ir_platform_bridge_process_case_runs_offline_without_crash():
    bridge = IRPlatformBridge()
    bridge.thehive.url = "http://127.0.0.1:65531"
    bridge.cortex.url = "http://127.0.0.1:65532"
    bridge.misp.url = "http://127.0.0.1:65533"
    bridge.dfir_iris.url = "http://127.0.0.1:65534"
    result = bridge.process_case(_sample_case())
    assert "thehive" in result
    assert "enrichments" in result
    assert "misp" in result
    assert "dfir_iris" in result


def test_ir_platform_bridge_enrich_observables_returns_each_result():
    bridge = IRPlatformBridge()
    bridge.cortex.url = "http://127.0.0.1:65532"
    observables = [
        Observable(observable_type=ObservableType.IP_ADDRESS, value="203.0.113.11", source_case_id="case-x"),
        Observable(observable_type=ObservableType.DOMAIN, value="evil.example", source_case_id="case-x"),
    ]
    results = bridge.enrich_observables(observables)
    assert len(results) == len(observables)
