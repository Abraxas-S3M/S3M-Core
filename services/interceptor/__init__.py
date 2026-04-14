"""
S3M Interceptor Drone Guidance Computer

Replicates the Krechet 9C905-2 terminal capability: real-time guidance of
interceptor drones to within 200-300m of moving aerial targets using
proportional navigation, with autonomous handoff for terminal engagement.

Data Flow:
  RadarManager -> fused target track -> GuidanceComputer -> SteeringCommands
  -> AutopilotAdapter -> AutopilotBridge -> interceptor drone
  -> PhaseManager monitors range -> AUTONOMOUS_HANDOFF at 200-300m
"""

from services.interceptor.models import (
    InterceptorState,
    GuidancePhase,
    GuidanceMode,
    InterceptGeometry,
    SteeringCommand,
    InterceptorConfig,
    GuidanceSolution,
    InterceptResult,
    HandoffCriteria,
)
from services.interceptor.geometry import InterceptGeometryComputer
from services.interceptor.guidance_laws import PurePursuit, LeadPursuit, ProportionalNavigation
from services.interceptor.phase_manager import GuidancePhaseManager
from services.interceptor.guidance_computer import GuidanceComputer

__all__ = [
    "InterceptorState",
    "GuidancePhase",
    "GuidanceMode",
    "InterceptGeometry",
    "SteeringCommand",
    "InterceptorConfig",
    "GuidanceSolution",
    "InterceptResult",
    "HandoffCriteria",
    "InterceptGeometryComputer",
    "PurePursuit",
    "LeadPursuit",
    "ProportionalNavigation",
    "GuidancePhaseManager",
    "GuidanceComputer",
]
