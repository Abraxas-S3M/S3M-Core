"""
S3M Layer 06 — Dashboard & Human-Machine Teaming
Unified operator interface with read-only access to all S3M layers.

Views:
1. COP (Common Operating Picture) — Tactical map with agents, threats, tracks, paths
2. LLM Monitor — Quad-engine status, inference metrics, audit log
3. Threat Dashboard — Threat feed, heatmap, sensor health
4. Autonomy Command — Agents, missions, swarm, XAI, human review queue
5. System Health — Jetson hardware, edge models, GPS, simulation, API health

Architecture:
  DashboardAggregator queries Python objects in-process (no inter-service HTTP).
  FastAPI serves the React frontend as static files.
  WebSocket pushes live alerts and updates.
"""

from src.dashboard.aggregator import DashboardAggregator
from src.dashboard.providers.alert_manager import AlertManager
from src.dashboard.providers.autonomy_dash_provider import AutonomyDashProvider
from src.dashboard.providers.cop_provider import COPDataProvider
from src.dashboard.providers.engagement_provider import EngagementProvider
from src.dashboard.providers.llm_monitor_provider import LLMMonitorProvider
from src.dashboard.providers.mission_provider import MissionProvider
from src.dashboard.providers.platform_provider import PlatformProvider
from src.dashboard.providers.system_health_provider import SystemHealthProvider
from src.dashboard.providers.threat_dash_provider import ThreatDashProvider
from src.dashboard.websocket_manager import WebSocketManager

__all__ = [
    "DashboardAggregator",
    "COPDataProvider",
    "LLMMonitorProvider",
    "ThreatDashProvider",
    "AutonomyDashProvider",
    "SystemHealthProvider",
    "PlatformProvider",
    "EngagementProvider",
    "MissionProvider",
    "AlertManager",
    "WebSocketManager",
]
