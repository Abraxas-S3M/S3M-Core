"""Unit tests for sustainment prediction ordering."""

from __future__ import annotations

from types import SimpleNamespace

import src.logistics.reliability_analyzer as reliability_module
from src.api.gui_bridge.adapters.sustainment_adapter import SustainmentAdapter


def test_get_predictions_sorted_by_lowest_rul(monkeypatch):
    assets = [
        SimpleNamespace(
            asset_id="ast-urgent",
            designation="Jet 1",
            asset_type="FIGHTER_JET",
            operating_hours=980.0,
        ),
        SimpleNamespace(
            asset_id="ast-routine",
            designation="Jet 2",
            asset_type="FIGHTER_JET",
            operating_hours=120.0,
        ),
        SimpleNamespace(
            asset_id="ast-soon",
            designation="Jet 3",
            asset_type="FIGHTER_JET",
            operating_hours=640.0,
        ),
    ]

    class FakeOperationalStore:
        def get_assets(self):
            return list(assets)

        def get_maintenance_history(self, asset_id: str):
            return []

    class FakeReliabilityAnalyzer:
        def __init__(self, operational_store=None):
            self._store = operational_store

        def estimate_rul(self, asset_type: str, hours_in_service: float) -> float:
            # Tactical priority model for this test: more hours means lower RUL.
            return max(0.0, 1000.0 - float(hours_in_service))

    monkeypatch.setattr(reliability_module, "OperationalStore", FakeOperationalStore)
    monkeypatch.setattr(reliability_module, "ReliabilityAnalyzer", FakeReliabilityAnalyzer)

    payload = SustainmentAdapter().get_predictions()
    predictions = payload["predictions"]

    assert [row["assetId"] for row in predictions] == ["ast-urgent", "ast-soon", "ast-routine"]
    assert [row["urgency"] for row in predictions] == ["critical", "medium", "low"]
    assert predictions[0]["estimatedRULHours"] == 20.0

