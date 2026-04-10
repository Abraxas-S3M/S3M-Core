"""enchat (extensions) secure communications integration wrapper."""

from __future__ import annotations

import importlib

EnchatextensionsAdapter = importlib.import_module(
    "packages.integrations.comms.enchat-extensions.adapter"
).EnchatextensionsAdapter

__all__ = ["EnchatextensionsAdapter"]
