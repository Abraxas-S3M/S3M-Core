"""Shared runtime state for Phase 19 intelligence subsystems.

This module centralizes singleton subsystem instances so API routes,
dashboard providers, and orchestration managers share one in-memory state.
"""

from __future__ import annotations

from typing import Any

from src.apps.intel.briefings import BriefingGenerator
from src.apps.intel.monitoring import GeopoliticalMonitor
from src.apps.intel.osint import OSINTCollector

_STATE: dict[str, Any] | None = None


def get_shared_intel_state() -> dict[str, Any]:
    global _STATE
    if _STATE is None:
        collector = OSINTCollector()
        monitor = GeopoliticalMonitor()
        briefing = BriefingGenerator(collector=collector)
        # Tactical context: share warning/monitor handles so briefing and collector
        # reflect current escalation indicators in one fused operating picture.
        setattr(collector, "warning_system", monitor.early_warning)
        setattr(collector, "monitor", monitor)
        _STATE = {
            "collector": collector,
            "monitor": monitor,
            "briefing": briefing,
            "brief_history": {"daily": [], "weekly": []},
        }
    return _STATE

