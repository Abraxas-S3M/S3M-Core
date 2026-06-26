"""COP backend package for dashboard-ready operational picture delivery.

This package is the first functional S3M-Core C4ISR/COP integration layer: it
ingests deterministic demo/tactical data through an open C4ISR adapter seam,
normalizes it into the S3M COP schema, serves it over REST + WebSocket, and
publishes AI-ready events as the bridge toward the future quad-engine reasoning
orchestrator. It performs no training, sync, or live LLM calls.
"""

from src.cop.adapters.open_c4isr_adapter import OpenC4ISRAdapter
from src.cop.cop_models import (
    CopAlert,
    CopDecision,
    CopFeature,
    CopFeedItem,
    CopMapConfig,
    CopPanelState,
    CopState,
    CopTheater,
    CopTrack,
)
from src.cop.cop_service import CopService, SUPPORTED_TRACKS
from src.cop.demo_tracks import DEMO_TRACKS, DemoScenario, build_scenario
from src.cop.event_bus import (
    AIContext,
    CopEvent,
    CopEventBus,
    build_event,
    get_event_bus,
)

__all__ = [
    "CopService",
    "SUPPORTED_TRACKS",
    "DEMO_TRACKS",
    "DemoScenario",
    "build_scenario",
    "OpenC4ISRAdapter",
    "AIContext",
    "CopEvent",
    "CopEventBus",
    "build_event",
    "get_event_bus",
    "CopAlert",
    "CopDecision",
    "CopFeature",
    "CopFeedItem",
    "CopMapConfig",
    "CopPanelState",
    "CopState",
    "CopTheater",
    "CopTrack",
]
