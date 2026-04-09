"""DFIR-IRIS incident response integration adapter for S3M."""

from __future__ import annotations

import importlib

DfirIrisAdapter = importlib.import_module("packages.integrations.cyber.dfir-iris.adapter").DfirIrisAdapter

__all__ = ["DfirIrisAdapter"]
