"""Tests for risk workspace adapter behavior."""

from __future__ import annotations

from src.api.gui_bridge.adapters.risk_adapter import RiskAdapter


class _FakeThreatProvider:
    def get_threat_stats(self):
        return {
            "total_events": 10,
            "by_level": {"CRITICAL": 2, "HIGH": 3, "MEDIUM": 1},
            "by_category": {"CYBER": 5, "AIR": 5},
            "active_sensors": 4,
        }


class _BrokenThreatProvider:
    def get_threat_stats(self):
        raise RuntimeError("provider unavailable")


def test_get_metrics_builds_domains_composite_and_forecast(monkeypatch) -> None:
    import src.dashboard.providers.threat_dash_provider as provider_module

    monkeypatch.setattr(provider_module, "ThreatDashProvider", _FakeThreatProvider)
    adapter = RiskAdapter()

    metrics = adapter.get_metrics()
    assert 0 <= metrics.composite <= 100
    assert len(metrics.domains) == 4
    assert [d.domain for d in metrics.domains] == ["air", "cyber", "intel", "logistics"]
    assert len(metrics.forecast) == 4
    assert all(0 <= point.score <= 100 for point in metrics.forecast)
    assert any(driver.name == "ISR coverage active" for driver in metrics.drivers)


def test_get_threat_stats_falls_back_on_provider_error(monkeypatch) -> None:
    import src.dashboard.providers.threat_dash_provider as provider_module

    monkeypatch.setattr(provider_module, "ThreatDashProvider", _BrokenThreatProvider)
    adapter = RiskAdapter()
    fallback = adapter._get_threat_stats()
    assert fallback == {"total_events": 0, "by_level": {}, "by_category": {}, "active_sensors": 0}


def test_compute_composite_defaults_when_no_domains() -> None:
    assert RiskAdapter._compute_composite([]) == 50
