"""HOOL autonomy extension for envelope-bounded autonomous missions.

Military context:
This package enables pre-authorized human-out-of-loop operations where tactical
platforms can act autonomously only inside a commander-approved mission envelope.
"""

from services.autonomy.hool_extension.envelope_checker import EnvelopeChecker
from services.autonomy.hool_extension.hool_agent import HOOLAgent
from services.autonomy.hool_extension.models import (
    CompanionCompute,
    EnvelopeViolation,
    HOOLDecision,
    HOOLMissionState,
    MissionEnvelope,
    PlatformClass,
)
from services.autonomy.hool_extension.platform_packager import PlatformPackager

__all__ = [
    "PlatformClass",
    "CompanionCompute",
    "MissionEnvelope",
    "EnvelopeViolation",
    "HOOLDecision",
    "HOOLMissionState",
    "EnvelopeChecker",
    "HOOLAgent",
    "PlatformPackager",
]
