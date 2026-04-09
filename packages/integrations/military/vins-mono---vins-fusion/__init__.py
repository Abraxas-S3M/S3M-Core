"""VINS-Mono / VINS-Fusion military integration package."""

from __future__ import annotations

import importlib

VinsMonoVinsAdapter = importlib.import_module(
    "packages.integrations.military.vins-mono---vins-fusion.adapter"
).VinsMonoVinsAdapter

__all__ = ["VinsMonoVinsAdapter"]
