"""allegro/ralph maintenance integration adapter for S3M."""

from __future__ import annotations

import importlib

AllegroralphAdapter = importlib.import_module(
    "packages.integrations.maintenance.allegro-ralph.adapter"
).AllegroralphAdapter

__all__ = ["AllegroralphAdapter"]
