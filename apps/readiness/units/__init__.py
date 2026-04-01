"""Unit manning and deployment eligibility subpackage."""

from apps.readiness.units.eligibility_engine import EligibilityEngine
from apps.readiness.units.manning_manager import UnitManningManager

__all__ = ["UnitManningManager", "EligibilityEngine"]

