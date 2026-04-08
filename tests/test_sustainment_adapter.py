"""Unit tests for sustainment adapter service wiring and fallbacks."""

from __future__ import annotations

from typing import Any

import services.maintenance.predictive as predictive_module
import src.logistics.supply_chain_twin as twin_module
import src.training.cpu_adaptation.stream_learner as stream_module
from src.api.gui_bridge.adapters.sustainment_adapter import SustainmentAdapter


def test_get_predictions_reads_predictive_engine_and_logs(monkeypatch) -> None:
    calls: dict[str, Any] = {}

    class FakePredictiveMaintenanceEngine:
        def get_predictions(self):  # noqa: ANN001
            return [{"asset_id": "asset-1", "risk_level": "high"}]

    def fake_log_fleet_maintenance_training_sample(  # noqa: ANN001
        fleet_health=None, maintenance_outcomes=None, output_path=None
    ):
        calls["fleet_health"] = fleet_health
        calls["maintenance_outcomes"] = maintenance_outcomes
        return {"ok": True}

    monkeypatch.setattr(
        predictive_module,
        "PredictiveMaintenanceEngine",
        FakePredictiveMaintenanceEngine,
    )
    monkeypatch.setattr(
        stream_module,
        "log_fleet_maintenance_training_sample",
        fake_log_fleet_maintenance_training_sample,
    )

    data = SustainmentAdapter().get_predictions()
    assert len(data["predictions"]) == 1
    assert data["predictions"][0]["asset_id"] == "asset-1"
    assert "updatedAt" in data
    assert calls["maintenance_outcomes"][0]["risk_level"] == "high"


def test_get_supply_twin_reads_status_from_twin(monkeypatch) -> None:
    class FakeSupplyChainTwin:
        def get_status(self) -> dict:
            return {"alerts": [{"depot": "d-1"}], "sim_day": 2}

    monkeypatch.setattr(twin_module, "SupplyChainTwin", FakeSupplyChainTwin)

    data = SustainmentAdapter().get_supply_twin()
    assert "updatedAt" in data
    assert data["supplyChain"]["sim_day"] == 2
    assert data["supplyChain"]["alerts"][0]["depot"] == "d-1"


def test_get_supply_twin_falls_back_to_supply(monkeypatch) -> None:
    class BrokenSupplyChainTwin:
        def __init__(self) -> None:
            raise RuntimeError("unavailable")

    adapter = SustainmentAdapter()
    monkeypatch.setattr(twin_module, "SupplyChainTwin", BrokenSupplyChainTwin)
    monkeypatch.setattr(adapter, "get_supply", lambda: {"categories": [], "updatedAt": "fallback"})

    data = adapter.get_supply_twin()
    assert data == {"categories": [], "updatedAt": "fallback"}


def test_get_fleet_logs_snapshot_for_training(monkeypatch) -> None:
    calls: dict[str, Any] = {}
    adapter = SustainmentAdapter()

    def fake_log_fleet_maintenance_training_sample(  # noqa: ANN001
        fleet_health=None, maintenance_outcomes=None, output_path=None
    ):
        calls["fleet_health"] = fleet_health
        calls["maintenance_outcomes"] = maintenance_outcomes
        return {"ok": True}

    monkeypatch.setattr(
        stream_module,
        "log_fleet_maintenance_training_sample",
        fake_log_fleet_maintenance_training_sample,
    )

    payload = adapter.get_fleet()
    assert "units" in payload
    assert "updatedAt" in payload
    assert calls["fleet_health"]["units"] == payload["units"]
    assert calls["maintenance_outcomes"] is None
