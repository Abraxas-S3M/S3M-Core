"""Captum integration adapter for S3M."""

from __future__ import annotations

import importlib

CaptumAdapter = importlib.import_module("packages.integrations.hmi.captum.adapter").CaptumAdapter

__all__ = ["CaptumAdapter"]
