"""IT Security Management System Dashboard integration adapter for S3M."""

from __future__ import annotations

import importlib

ItSecurityManagementSystemAdapter = importlib.import_module(
    "packages.integrations.cyber.it-security-management-system-dashboard.adapter"
).ItSecurityManagementSystemAdapter

__all__ = ["ItSecurityManagementSystemAdapter"]
