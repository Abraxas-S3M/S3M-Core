"""VSLAM-UAV navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

VslamUavAdapter = importlib.import_module(
    "packages.integrations.navigation.vslam-uav.adapter"
).VslamUavAdapter

__all__ = ["VslamUavAdapter"]
