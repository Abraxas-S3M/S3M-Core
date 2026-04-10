"""Military-Management-System readiness integration adapter for S3M."""

from __future__ import annotations

import importlib

MilitaryManagementSystemAdapter = importlib.import_module(
    "packages.integrations.readiness.military-management-system.adapter"
).MilitaryManagementSystemAdapter

__all__ = ["MilitaryManagementSystemAdapter"]
