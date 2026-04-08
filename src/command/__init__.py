"""Command-layer interfaces for tactical mission authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.command.mission_command_engine import MissionCommandEngine

__all__ = ["MissionCommandEngine"]


def __getattr__(name: str):
    if name == "MissionCommandEngine":
        from src.command.mission_command_engine import MissionCommandEngine

        return MissionCommandEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
