"""Unit tests for logistics reliability analysis."""

from __future__ import annotations

from types import SimpleNamespace

from src.logistics.reliability_analyzer import ReliabilityAnalyzer


class _FakeOperationalStore:
    def __init__(self, assets, history_by_asset_id):
        self._assets = assets
        self._history_by_asset_id = history_by_asset_id

    def get_assets(self):
        return list(self._assets)

    def get_maintenance_history(self, asset_id: str):
        return list(self._history_by_asset_id.get(asset_id, []))


def _asset(asset_id: str, asset_type: str, operating_hours: float):
    return SimpleNamespace(
        asset_id=asset_id,
        asset_type=asset_type,
        operating_hours=operating_hours,
    )


def _record(hours_at_maintenance: float):
    return SimpleNamespace(hours_at_maintenance=hours_at_maintenance)


def test_estimate_rul_drops_as_hours_increase():
    assets = [
        _asset("ast-001", "FIGHTER_JET", 700.0),
        _asset("ast-002", "FIGHTER_JET", 1100.0),
        _asset("ast-003", "FIGHTER_JET", 500.0),
    ]
    history = {
        "ast-001": [_record(620.0)],
        "ast-002": [_record(980.0)],
        "ast-003": [],
    }
    analyzer = ReliabilityAnalyzer(operational_store=_FakeOperationalStore(assets, history))

    early_life = analyzer.estimate_rul(asset_type="FIGHTER_JET", hours_in_service=250.0)
    late_life = analyzer.estimate_rul(asset_type="FIGHTER_JET", hours_in_service=900.0)

    assert early_life >= 0.0
    assert late_life >= 0.0
    assert late_life <= early_life


def test_survival_curve_probabilities_are_bounded():
    assets = [_asset("ast-100", "TANK", 1200.0), _asset("ast-101", "TANK", 1800.0)]
    history = {"ast-100": [_record(950.0)], "ast-101": [_record(1450.0)]}
    analyzer = ReliabilityAnalyzer(operational_store=_FakeOperationalStore(assets, history))

    curve = analyzer.get_survival_curve(asset_type="TANK")

    assert curve
    for _, probability in curve:
        assert 0.0 <= probability <= 1.0


def test_unknown_asset_type_uses_safe_fallback_life():
    analyzer = ReliabilityAnalyzer(operational_store=_FakeOperationalStore([], {}))
    remaining = analyzer.estimate_rul(asset_type="EXPERIMENTAL", hours_in_service=100.0)
    assert 5899.0 <= remaining <= 5901.0

