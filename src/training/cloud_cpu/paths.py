"""Filesystem path conventions for cloud CPU training state.

These paths keep tactical training telemetry and control files in local disk
so API and trainer processes can coordinate in air-gapped deployments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TrainingTrack(str, Enum):
    """Supported domain training tracks for tactical model adaptation."""

    SAUDI_MOD = "saudi_mod"
    UKRAINE_MOD = "ukraine_mod"
    NATO = "nato"


@dataclass(frozen=True)
class TrackPaths:
    """Per-track filesystem locations for run and promoted checkpoints."""

    base: Path
    runs: Path
    promoted: Path


class StatePaths:
    """Resolve and create cloud training state directories."""

    def __init__(self, root: Path | None = None) -> None:
        # Tactical deployments can redirect state location per mission profile.
        self.root = root or Path(os.environ.get("S3M_TRAINING_STATE_DIR", "state"))
        self.metrics = self.root / "metrics"
        self.locks = self.root / "locks"
        self.checkpoints = self.root / "checkpoints"
        self._ensure_base_dirs()

    def _ensure_base_dirs(self) -> None:
        self.metrics.mkdir(parents=True, exist_ok=True)
        self.locks.mkdir(parents=True, exist_ok=True)
        self.checkpoints.mkdir(parents=True, exist_ok=True)

    def for_track(self, track: TrainingTrack) -> TrackPaths:
        """Return per-track checkpoint directories and ensure they exist."""
        base = self.checkpoints / track.value
        runs = base / "runs"
        promoted = base / "promoted"
        runs.mkdir(parents=True, exist_ok=True)
        promoted.mkdir(parents=True, exist_ok=True)
        return TrackPaths(base=base, runs=runs, promoted=promoted)
