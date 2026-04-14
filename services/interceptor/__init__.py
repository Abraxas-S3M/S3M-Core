"""Interceptor guidance services for local air-defense engagements.

Military context:
Provides offline-capable interceptor guidance primitives for layered defense
where the node may need to continue engagements under comms disruption.
"""

from services.interceptor.guidance_computer import GuidanceComputer, GuidancePhase, PhaseManager
from services.interceptor.interceptor_manager import InterceptorManager
from services.interceptor.models import (
    GuidanceSolution,
    InterceptorConfig,
    InterceptorState,
    InterceptResult,
)

__all__ = [
    "GuidanceComputer",
    "GuidancePhase",
    "GuidanceSolution",
    "InterceptorConfig",
    "InterceptorManager",
    "InterceptorState",
    "InterceptResult",
    "PhaseManager",
]
