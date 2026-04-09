"""Cybersim SOC simulator integration adapter for S3M."""

from __future__ import annotations

import importlib

CybersimSocSimulatorAdapter = importlib.import_module(
    "packages.integrations.cyber.cybersim-soc-simulator.adapter"
).CybersimSocSimulatorAdapter

__all__ = ["CybersimSocSimulatorAdapter"]
