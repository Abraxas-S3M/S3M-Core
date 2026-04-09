"""mav-multiagent-ws military integration adapter package for S3M."""

from __future__ import annotations

import importlib

MavMultiagentWsAdapter = importlib.import_module(
    "packages.integrations.military.mav-multiagent-ws.adapter"
).MavMultiagentWsAdapter

__all__ = ["MavMultiagentWsAdapter"]
