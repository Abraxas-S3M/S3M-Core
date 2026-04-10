"""Kinematic Arbiter sensor-fusion integration wrapper for S3M."""

from __future__ import annotations

import importlib

KinematicArbiterAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.kinematic-arbiter.adapter"
).KinematicArbiterAdapter

__all__ = ["KinematicArbiterAdapter"]
