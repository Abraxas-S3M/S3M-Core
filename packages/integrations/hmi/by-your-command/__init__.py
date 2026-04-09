"""By Your Command HMI integration adapter for S3M."""

from __future__ import annotations

import importlib

ByYourCommandAdapter = importlib.import_module(
    "packages.integrations.hmi.by-your-command.adapter"
).ByYourCommandAdapter

__all__ = ["ByYourCommandAdapter"]
