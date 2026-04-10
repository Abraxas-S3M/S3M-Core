"""hr-management-system readiness integration adapter for S3M."""

from __future__ import annotations

import importlib

HrManagementSystemAdapter = importlib.import_module(
    "packages.integrations.readiness.hr-management-system.adapter"
).HrManagementSystemAdapter

__all__ = ["HrManagementSystemAdapter"]
