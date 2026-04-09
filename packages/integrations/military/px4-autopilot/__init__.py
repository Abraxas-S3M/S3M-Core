"""PX4-Autopilot military integration package."""

from __future__ import annotations

import importlib

Px4AutopilotAdapter = importlib.import_module(
    "packages.integrations.military.px4-autopilot.adapter"
).Px4AutopilotAdapter

__all__ = ["Px4AutopilotAdapter"]
