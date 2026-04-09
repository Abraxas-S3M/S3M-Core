"""Military Management FE integration adapter for S3M."""

from __future__ import annotations

import importlib

MilitaryManagementFeAdapter = importlib.import_module(
    "packages.integrations.military.military-management-fe.adapter"
).MilitaryManagementFeAdapter

__all__ = ["MilitaryManagementFeAdapter"]
