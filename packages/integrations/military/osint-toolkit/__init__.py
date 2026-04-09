"""osint_toolkit integration adapter for S3M."""

from __future__ import annotations

import importlib

OsintToolkitAdapter = importlib.import_module(
    "packages.integrations.military.osint-toolkit.adapter"
).OsintToolkitAdapter

__all__ = ["OsintToolkitAdapter"]
