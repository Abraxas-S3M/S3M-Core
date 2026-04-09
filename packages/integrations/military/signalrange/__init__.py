"""S3M military integration wrapper for SignalRange."""

from __future__ import annotations

import importlib

SignalrangeAdapter = importlib.import_module(
    "packages.integrations.military.signalrange.adapter"
).SignalrangeAdapter

__all__ = ["SignalrangeAdapter"]
