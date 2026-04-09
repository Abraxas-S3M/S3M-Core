"""S3M military integration wrapper for awesome-threat-intelligence-adapt."""

from __future__ import annotations

import importlib

AwesomeThreatIntelligenceadaptAdapter = importlib.import_module(
    "packages.integrations.military.awesome-threat-intelligence-adapt.adapter"
).AwesomeThreatIntelligenceadaptAdapter

__all__ = ["AwesomeThreatIntelligenceadaptAdapter"]
