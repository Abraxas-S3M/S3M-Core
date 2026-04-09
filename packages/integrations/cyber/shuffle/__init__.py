"""Shuffle SOAR integration adapter for S3M."""

from __future__ import annotations

import importlib

ShuffleAdapter = importlib.import_module("packages.integrations.cyber.shuffle.adapter").ShuffleAdapter

__all__ = ["ShuffleAdapter"]
