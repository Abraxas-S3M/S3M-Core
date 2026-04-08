"""Unit tests for command workspace GUI bridge adapter."""

from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


def _install_gui_schema_stubs(monkeypatch) -> types.ModuleType:
    schema_mod = types.ModuleType("src.api.gui_bridge.models.gui_schemas")

    class SeverityLevel(str, Enum):
        LOW = "LOW"
        MEDIUM = "MEDIUM"
        HIGH = "HIGH"
        CRITICAL = "CRITICAL"

    class DecisionStatus(str, Enum):
        PENDING = "PENDING"

    class TrendDirection(str, Enum):
        UP = "up"
        DOWN = "down"
        STEADY = "steady"

    @dataclass
    class GUIThreatItem:
        id: str
        label: str
        level: SeverityLevel
        domain: str
        summary: str
        updatedAt: str

    @dataclass
    class GUIDecision:
        id: str
        title: str
        risk: int
        confidence: int
        description: str
        status: DecisionStatus
        severity: SeverityLevel
        updatedAt: str

    @dataclass
    class GUIDirectiveItem:
        id: str
        title: str
        authority: str
        status: str
        details: str
        updatedAt: str

    @dataclass
    class GUITimelineEventData:
        events: list[dict[str, Any]]
        updatedAt: str

    @dataclass
    class GUIOverviewMetrics:
        readinessScore: int
        activeMissions: int
        assetAvailability: int
        openRisks: int

    @dataclass
    class GUIOperationalContextData:
        threats: list[GUIThreatItem]
        decisions: list[GUIDecision]
        directives: list[GUIDirectiveItem]
        updatedAt: str
        metrics: Optional[GUIOverviewMetrics] = None

    @dataclass
    class GUIRiskDomain:
        domain: str
        score: int
        trend: TrendDirection

    @dataclass
    class GUIRiskForecast:
        timestamp: str
        score: int

    @dataclass
    class GUIRiskDriver:
        name: str
        impact: float
        direction: str

    @dataclass
    class GUIRiskData:
        composite: int
        domains: list[GUIRiskDomain]
        forecast: list[GUIRiskForecast]
        drivers: list[GUIRiskDriver]
        updatedAt: str

    schema_mod.SeverityLevel = SeverityLevel
    schema_mod.DecisionStatus = DecisionStatus
    schema_mod.TrendDirection = TrendDirection
    schema_mod.GUIThreatItem = GUIThreatItem
    schema_mod.GUIDecision = GUIDecision
    schema_mod.GUIDirectiveItem = GUIDirectiveItem
    schema_mod.GUITimelineEventData = GUITimelineEventData
    schema_mod.GUIOverviewMetrics = GUIOverviewMetrics
    schema_mod.GUIOperationalContextData = GUIOperationalContextData
    schema_mod.GUIRiskDomain = GUIRiskDomain
    schema_mod.GUIRiskForecast = GUIRiskForecast
    schema_mod.GUIRiskDriver = GUIRiskDriver
    schema_mod.GUIRiskData = GUIRiskData
    monkeypatch.setitem(sys.modules, "src.api.gui_bridge.models.gui_schemas", schema_mod)
    return schema_mod


def _install_timeline_stub(monkeypatch) -> types.ModuleType:
    timeline_mod = types.ModuleType("src.api.gui_bridge.timeline_service")

    class _TimelineService:
        def __init__(self) -> None:
            self.emitted: list[dict[str, Any]] = []

        def query(self, category: str = None, limit: int = 50) -> list[dict[str, Any]]:
            return [{"id": "EVT-1", "category": category or "all", "limit": limit}]

        def emit(
            self,
            title: str,
            category: str,
            severity: str = "MEDIUM",
            details: str = "",
        ) -> None:
            self.emitted.append(
                {
                    "title": title,
                    "category": category,
                    "severity": severity,
                    "details": details,
                }
            )

    timeline_mod.timeline_service = _TimelineService()
    monkeypatch.setitem(sys.modules, "src.api.gui_bridge.timeline_service", timeline_mod)
    return timeline_mod


def _install_dashboard_stub(monkeypatch, *, threats: list[dict[str, Any]], review_queue: list[dict[str, Any]]) -> None:
    dash_mod = types.ModuleType("src.dashboard.aggregator")

    class _ThreatProvider:
        def get_threat_feed(self, limit: int = 20) -> list[dict[str, Any]]:
            return threats[:limit]

    class _AutonomyProvider:
        def get_review_queue(self) -> list[dict[str, Any]]:
            return list(review_queue)

    class DashboardAggregator:
        def __init__(self) -> None:
            self.threat_provider = _ThreatProvider()
            self.autonomy_provider = _AutonomyProvider()

        def get_overview(self) -> dict[str, Any]:
            return {
                "timestamp": "2026-04-04T00:00:00+00:00",
                "readiness_score": 0.72,
                "active_missions": 4,
                "asset_availability": 0.85,
            }

    dash_mod.DashboardAggregator = DashboardAggregator
    monkeypatch.setitem(sys.modules, "src.dashboard.aggregator", dash_mod)


def _reload_command_adapter():
    sys.modules.pop("src.api.gui_bridge.adapters.command_adapter", None)
    return importlib.import_module("src.api.gui_bridge.adapters.command_adapter")


def test_command_adapter_maps_live_dashboard_data(monkeypatch):
    schemas = _install_gui_schema_stubs(monkeypatch)
    timeline_mod = _install_timeline_stub(monkeypatch)
    _install_dashboard_stub(
        monkeypatch,
        threats=[
            {
                "id": "TH-100",
                "title": "Missile launch warning",
                "confidence": 0.9,
                "category": "KINETIC",
                "description": "Inbound launch detected from sector bravo.",
                "timestamp": "2026-04-04T01:00:00+00:00",
            }
        ],
        review_queue=[
            {
                "id": "DEC-1",
                "type": "engage",
                "risk_score": 0.72,
                "confidence": 0.88,
                "reasoning_snippet": "Track probability exceeds engagement threshold.",
                "timestamp": "2026-04-04T01:05:00+00:00",
            }
        ],
    )

    doctrine_mod = types.ModuleType("src.doctrine")

    class DoctrineProfileManager:
        def list_profiles(self) -> list[dict[str, str]]:
            return [
                {
                    "name": "ROE ALPHA",
                    "authority": "Joint Command",
                    "description": "Maintain positive identification before strike authorization.",
                }
            ]

    doctrine_mod.DoctrineProfileManager = DoctrineProfileManager
    monkeypatch.setitem(sys.modules, "src.doctrine", doctrine_mod)

    adapter_module = _reload_command_adapter()
    adapter = adapter_module.CommandAdapter()

    context = adapter.get_operational_context()
    assert context.updatedAt == "2026-04-04T00:00:00+00:00"
    assert context.threats[0].id == "TH-100"
    assert context.threats[0].level == schemas.SeverityLevel.CRITICAL
    assert context.threats[0].domain == "kinetic"
    assert context.decisions[0].risk == 72
    assert context.decisions[0].confidence == 88
    assert context.decisions[0].status == schemas.DecisionStatus.PENDING
    assert context.directives[0].title == "ROE ALPHA"
    assert context.metrics is not None
    assert context.metrics.readinessScore == 72
    assert context.metrics.activeMissions == 4
    assert context.metrics.assetAvailability == 85
    assert context.metrics.openRisks == 1
    assert timeline_mod.timeline_service.emitted[0]["title"] == "Metrics snapshot"

    timeline = adapter.get_timeline_events(category="threat", limit=3)
    assert timeline.events[0]["category"] == "threat"
    assert timeline.events[0]["limit"] == 3


def test_command_adapter_fallbacks_seed_operational_defaults(monkeypatch):
    schemas = _install_gui_schema_stubs(monkeypatch)
    _install_timeline_stub(monkeypatch)
    _install_dashboard_stub(monkeypatch, threats=[], review_queue=[])

    doctrine_mod = types.ModuleType("src.doctrine")

    class DoctrineProfileManager:
        def __init__(self) -> None:
            raise RuntimeError("Doctrine profile store unavailable")

    doctrine_mod.DoctrineProfileManager = DoctrineProfileManager
    monkeypatch.setitem(sys.modules, "src.doctrine", doctrine_mod)

    adapter_module = _reload_command_adapter()
    adapter = adapter_module.CommandAdapter()
    context = adapter.get_operational_context()

    assert context.threats[0].id == "T-SYS-001"
    assert context.threats[0].level == schemas.SeverityLevel.LOW
    assert len(context.decisions) == 3
    assert context.decisions[0].severity == schemas.SeverityLevel.CRITICAL
    assert context.directives[0].id == "DIR-1"
    assert context.metrics is not None
    assert context.metrics.readinessScore == 72
    assert context.metrics.activeMissions == 4
    assert context.metrics.assetAvailability == 85
    assert context.metrics.openRisks == 0
