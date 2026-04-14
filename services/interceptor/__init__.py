"""Interceptor guidance subsystem.

Military context:
Exports deterministic command-guidance primitives used for short-range
interception control loops in contested air-defense operations.
"""

from services.interceptor.geometry import InterceptGeometryComputer
from services.interceptor.guidance_computer import GuidanceComputer
from services.interceptor.guidance_laws import LeadPursuit, ProportionalNavigation, PurePursuit
from services.interceptor.models import (
    GuidanceMode,
    GuidancePhase,
    GuidanceSolution,
    HandoffConfig,
    InterceptorConfig,
    InterceptorState,
    InterceptGeometry,
    InterceptResult,
    SteeringCommand,
)
from services.interceptor.phase_manager import GuidancePhaseManager

__all__ = [
    "GuidanceComputer",
    "GuidanceMode",
    "GuidancePhase",
    "GuidancePhaseManager",
    "GuidanceSolution",
    "HandoffConfig",
    "InterceptGeometry",
    "InterceptGeometryComputer",
    "InterceptResult",
    "InterceptorConfig",
    "InterceptorState",
    "LeadPursuit",
    "ProportionalNavigation",
    "PurePursuit",
    "SteeringCommand",
]
