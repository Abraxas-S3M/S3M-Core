"""ORB_SLAM3 military integration package."""

from __future__ import annotations

import importlib

OrbSlam3Adapter = importlib.import_module(
    "packages.integrations.military.orb-slam3.adapter"
).OrbSlam3Adapter

__all__ = ["OrbSlam3Adapter"]
