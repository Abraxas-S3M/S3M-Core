"""UAVs_Meet_LLMs integration adapter for HMI workflows."""

from __future__ import annotations

import importlib

UavsMeetLlmsAdapter = importlib.import_module(
    "packages.integrations.hmi.uavs-meet-llms.adapter"
).UavsMeetLlmsAdapter

__all__ = ["UavsMeetLlmsAdapter"]
