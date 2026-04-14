"""Interceptor guidance subsystem for Krechet-equivalent C2 behavior.

Military context:
Provides deterministic, offline guidance components that steer interceptor
UAVs to the 200-300 m autonomous handoff window against aerial targets.
"""

from services.interceptor.guidance_computer import InterceptorGuidanceComputer
from services.interceptor.interceptor_manager import InterceptorManager
from services.interceptor.models import (
    GuidanceMode,
    GuidancePhase,
    GuidanceSolution,
    HandoffCriteria,
    InterceptGeometry,
    InterceptResult,
    InterceptorConfig,
    InterceptorState,
    SteeringCommand,
)

__all__ = [
    "GuidanceMode",
    "GuidancePhase",
    "GuidanceSolution",
    "HandoffCriteria",
    "InterceptGeometry",
    "InterceptResult",
    "InterceptorConfig",
    "InterceptorGuidanceComputer",
    "InterceptorManager",
    "InterceptorState",
    "SteeringCommand",
]
