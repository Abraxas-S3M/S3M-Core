"""glpi-project/glpi maintenance integration adapter for S3M."""

from __future__ import annotations

import importlib

GlpiProjectglpiAdapter = importlib.import_module(
    "packages.integrations.maintenance.glpi-project-glpi.adapter"
).GlpiProjectglpiAdapter

__all__ = ["GlpiProjectglpiAdapter"]
