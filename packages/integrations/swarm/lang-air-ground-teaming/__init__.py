"""lang-air-ground-teaming swarm integration adapter for S3M."""

from __future__ import annotations

import importlib

LangAirGroundTeamingAdapter = importlib.import_module(
    "packages.integrations.swarm.lang-air-ground-teaming.adapter"
).LangAirGroundTeamingAdapter

__all__ = ["LangAirGroundTeamingAdapter"]
