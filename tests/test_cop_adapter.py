"""Unit tests for COP GUI bridge adapter."""

from __future__ import annotations

import importlib.util
import sys
import types
from typing import Any


def _install_cop_provider_stub(monkeypatch) -> None:
    cop_mod = types.ModuleType("src.dashboard.providers.cop_provider")

    class COPDataProvider:
        def get_tracks(self) -> list[dict[str, Any]]:
            return [
                {
                    "id": "TRK-1",
                    "type": "aircraft",
                    "confidence": 0.91,
                    "threat_score": 0.86,
                    "correlated": ["TRK-2"],
                    "classification": "Hostile fixed-wing",
                    "last_update": "2026-04-04T02:00:00+00:00",
                },
                {
                    "id": "TRK-3",
                    "type": "network packet stream",
                    "confidence": 64,
                    "threat_score": 120,
                    "correlated": [],
                    "classification": "Potential C2 beaconing",
                    "last_update": "2026-04-04T02:10:00+00:00",
                },
            ]

        def get_threats(self) -> list[dict[str, Any]]:
            return [
                {
                    "id": "TH-1",
                    "level": "HIGH",
                    "category": "CYBER",
                    "confidence": 0.52,
                    "description": "Potential lateral movement indicators observed.",
                    "timestamp": "2026-04-04T02:15:00+00:00",
                }
            ]

    cop_mod.COPDataProvider = COPDataProvider
    monkeypatch.setitem(sys.modules, "src.dashboard.providers.cop_provider", cop_mod)


def _reload_cop_adapter():
    module_name = "src.api.gui_bridge.adapters.cop_adapter"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        "/workspace/src/api/gui_bridge/adapters/cop_adapter.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_cop_adapter_maps_tracks_and_threat_tracks(monkeypatch):
    _install_cop_provider_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()
    adapter = adapter_module.COPAdapter()

    tracks = adapter.get_tracks()
    assert len(tracks.tracks) == 2
    assert tracks.tracks[0].domain == "kinetic"
    assert tracks.tracks[0].confidence == 91
    assert tracks.tracks[0].severity == 86
    assert tracks.tracks[1].domain == "cyber"
    assert tracks.tracks[1].severity == 100

    threat_tracks = adapter.get_threat_tracks()
    assert len(threat_tracks.tracks) == 1
    assert threat_tracks.tracks[0].domain == "cyber"
    assert threat_tracks.tracks[0].confidence == 52
    assert threat_tracks.tracks[0].severity == 75


def test_cop_adapter_percent_and_domain_helpers(monkeypatch):
    _install_cop_provider_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()

    assert adapter_module.COPAdapter._to_percent(0.5) == 50
    assert adapter_module.COPAdapter._to_percent(150) == 100
    assert adapter_module.COPAdapter._to_percent(-10) == 0
    assert adapter_module.COPAdapter._infer_domain({"type": "sigint relay"}) == "intel"


def test_cop_adapter_get_enriched_tracks_merges_operational_and_fused(monkeypatch):
    _install_cop_provider_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()
    adapter = adapter_module.COPAdapter()

    class _FakeOperationalPictureService:
        def get_picture(self):
            return {
                "generated_at": "2026-04-08T08:00:00+00:00",
                "entities": [
                    {
                        "entity_id": "TRK-ENR-1",
                        "entity_type": "aircraft",
                        "classification": "Hostile aircraft",
                        "threat_level": "high",
                        "doctrine_adjusted_confidence": 0.82,
                        "position": [1200.0, 1800.0, 300.0],
                        "velocity": [90.0, 10.0, 0.0],
                        "sensor_sources": ["RADAR-01"],
                        "history": [
                            {"pos": [1100.0, 1700.0, 290.0], "ts": "2026-04-08T07:59:00+00:00"}
                        ],
                    }
                ],
            }

    class _FakeFusedTrack:
        def to_dict(self):
            return {
                "track_id": "TRK-ENR-1",
                "classification": "Hostile aircraft",
                "confidence": 0.9,
                "position": [1250.0, 1820.0, 320.0],
                "velocity": [95.0, 12.0, 0.0],
                "last_update": "2026-04-08T08:00:10+00:00",
                "sensor_sources": ["AIS"],
                "history": [{"pos": [1150.0, 1720.0, 300.0], "ts": "2026-04-08T07:59:30+00:00"}],
            }

    ops_module = types.ModuleType("src.runtime.operational_picture_service")
    ops_module.OperationalPictureService = _FakeOperationalPictureService
    monkeypatch.setitem(sys.modules, "src.runtime.operational_picture_service", ops_module)
    monkeypatch.setattr(adapter, "_get_confirmed_fused_tracks", lambda: [_FakeFusedTrack()])

    enriched = adapter.get_enriched_tracks()
    assert len(enriched.tracks) == 1
    track = enriched.tracks[0]
    assert track.id == "TRK-ENR-1"
    assert track.latitude is not None and track.longitude is not None
    assert track.speed is not None and track.heading is not None
    assert track.sourceAttribution is not None
    assert set(track.sourceAttribution) == {"AIS", "RADAR-01"}
    assert track.trackHistory is not None
    assert isinstance(track.recommendedAction, str) and track.recommendedAction


def test_cop_adapter_get_enriched_tracks_falls_back_to_tracks(monkeypatch):
    _install_cop_provider_stub(monkeypatch)
    adapter_module = _reload_cop_adapter()
    adapter = adapter_module.COPAdapter()

    class _BrokenOperationalPictureService:
        def __init__(self):
            raise RuntimeError("service unavailable")

    ops_module = types.ModuleType("src.runtime.operational_picture_service")
    ops_module.OperationalPictureService = _BrokenOperationalPictureService
    monkeypatch.setitem(sys.modules, "src.runtime.operational_picture_service", ops_module)

    fallback = adapter.get_enriched_tracks()
    assert len(fallback.tracks) == 2
