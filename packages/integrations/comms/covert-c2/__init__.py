"""Covert-C2 communications integration wrapper for S3M."""

from __future__ import annotations

import importlib

CovertC2Adapter = importlib.import_module(
    "packages.integrations.comms.covert-c2.adapter"
).CovertC2Adapter

__all__ = ["CovertC2Adapter"]
