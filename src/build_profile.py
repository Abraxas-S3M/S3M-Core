"""S3M build profile gates optional capabilities in customer deliverables.

Tactical deployments ship a hardened ``customer`` image without adversary-emulation
tooling; range and internal ``dev`` builds retain Caldera integration for exercises.
"""

from __future__ import annotations

import os
import sys
from enum import Enum


class BuildProfile(str, Enum):
    CUSTOMER = "customer"
    RANGE = "range"
    DEV = "dev"


_VALID = {p.value for p in BuildProfile}


def _is_production_runtime() -> bool:
    """True when the process is treated as a production edge deployment."""
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if os.environ.get("S3M_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    explicit = os.environ.get("S3M_PRODUCTION", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    mode = os.environ.get("DEPLOYMENT_MODE", "jetson_edge").strip().lower()
    return mode == "jetson_edge"


def get_build_profile() -> BuildProfile:
    """Resolve the active build profile from ``S3M_BUILD_PROFILE``.

    When unset, production runtimes default to ``customer``; local and CI test
    runs default to ``dev`` so integrators can exercise range features explicitly.
    """
    raw = os.environ.get("S3M_BUILD_PROFILE", "").strip().lower()
    if raw:
        if raw not in _VALID:
            raise ValueError(
                f"Invalid S3M_BUILD_PROFILE={raw!r}; expected one of {sorted(_VALID)}"
            )
        return BuildProfile(raw)
    if _is_production_runtime():
        return BuildProfile.CUSTOMER
    return BuildProfile.DEV


def offensive_tooling_enabled() -> bool:
    """Caldera / adversary-emulation integrations are range and dev only."""
    return get_build_profile() in {BuildProfile.RANGE, BuildProfile.DEV}
