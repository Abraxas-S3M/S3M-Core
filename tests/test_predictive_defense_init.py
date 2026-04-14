"""Unit tests for predictive defense package exports.

Military context:
These checks protect tactical integration contracts so downstream fire-control
modules receive the exact predictive-defense model symbols expected at import time.
"""

from __future__ import annotations

import importlib
import sys
import types

EXPECTED_EXPORTS = [
    "ThreatTrajectoryPrediction",
    "SwarmPrediction",
    "PrePositionCommand",
    "InterceptWindow",
    "PredictiveAlert",
    "DefensePosture",
]


def _build_stub_models_module() -> types.ModuleType:
    module = types.ModuleType("services.predictive_defense.models")
    for symbol in EXPECTED_EXPORTS:
        setattr(module, symbol, type(symbol, (), {}))
    return module


def test_predictive_defense_init_re_exports_expected_models(monkeypatch):
    stub_models = _build_stub_models_module()
    monkeypatch.setitem(sys.modules, "services.predictive_defense.models", stub_models)
    monkeypatch.delitem(sys.modules, "services.predictive_defense", raising=False)

    module = importlib.import_module("services.predictive_defense")

    assert module.__all__ == EXPECTED_EXPORTS
    for symbol in EXPECTED_EXPORTS:
        assert getattr(module, symbol) is getattr(stub_models, symbol)
