"""MoveIt motion planning navigation integration adapter for S3M."""

from __future__ import annotations

import importlib

MoveitmotionPlanningAdapter = importlib.import_module(
    "packages.integrations.navigation.moveit-motion-planning.adapter"
).MoveitmotionPlanningAdapter

__all__ = ["MoveitmotionPlanningAdapter"]
