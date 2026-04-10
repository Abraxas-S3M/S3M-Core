"""particle_filter integration adapter for S3M."""

from __future__ import annotations

import importlib

ParticleFilterAdapter = importlib.import_module(
    "packages.integrations.sensor_fusion.particle-filter.adapter"
).ParticleFilterAdapter

__all__ = ["ParticleFilterAdapter"]
