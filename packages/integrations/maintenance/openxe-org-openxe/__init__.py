"""OpenXE-org/OpenXE maintenance integration adapter for S3M."""

from __future__ import annotations

import importlib

OpenxeOrgopenxeAdapter = importlib.import_module(
    "packages.integrations.maintenance.openxe-org-openxe.adapter"
).OpenxeOrgopenxeAdapter

__all__ = ["OpenxeOrgopenxeAdapter"]
