"""mtc-cms readiness integration adapter for S3M."""

from __future__ import annotations

import importlib

MtcCmsAdapter = importlib.import_module(
    "packages.integrations.readiness.mtc-cms.adapter"
).MtcCmsAdapter

__all__ = ["MtcCmsAdapter"]
