"""Interceptor guidance and state-control package.

Military context:
Exports interceptor guidance models and transition logic for deterministic
command-and-control handoff in tactical air-defense engagements.
"""

from services.interceptor.models import GuidancePhase, HandoffCriteria, InterceptGeometry, InterceptorState
from services.interceptor.phase_manager import GuidancePhaseManager

__all__ = [
    "GuidancePhase",
    "GuidancePhaseManager",
    "HandoffCriteria",
    "InterceptGeometry",
    "InterceptorState",
]
