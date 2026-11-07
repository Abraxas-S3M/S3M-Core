"""Offensive cyber integrations for controlled tactical simulations (range/dev only)."""

from __future__ import annotations

from src.build_profile import BuildProfile, get_build_profile

if get_build_profile() == BuildProfile.CUSTOMER:
    raise ImportError(
        "services.cyber.offensive is excluded from customer builds "
        "(S3M_BUILD_PROFILE=customer)"
    )

from services.cyber.offensive.caldera_bridge import CalderaBridge

__all__ = ["CalderaBridge"]
