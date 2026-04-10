"""ejabberd comms integration wrapper for S3M."""

from __future__ import annotations

import importlib

EjabberdAdapter = importlib.import_module(
    "packages.integrations.comms.ejabberd.adapter"
).EjabberdAdapter

__all__ = ["EjabberdAdapter"]
