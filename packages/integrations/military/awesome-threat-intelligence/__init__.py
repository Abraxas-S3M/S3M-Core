"""awesome-threat-intelligence integration adapter for S3M."""

from __future__ import annotations

import importlib

AwesomeThreatIntelligenceAdapter = importlib.import_module(
    "packages.integrations.military.awesome-threat-intelligence.adapter"
).AwesomeThreatIntelligenceAdapter

__all__ = ["AwesomeThreatIntelligenceAdapter"]
