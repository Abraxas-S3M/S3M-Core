"""Canonical path contracts for cloud CPU training in tactical environments."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class TrainingTrack(str, Enum):
    """Domain training tracks for military scenario specialization."""

    SAUDI_MOD = "saudi_mod"
    UKRAINE_MOD = "ukraine_mod"
    NATO = "nato"
    SHARED = "shared"


@dataclass(frozen=True)
class TrackCheckpointPaths:
    """Track-specific checkpoint paths used by promotion and resume flows."""

    runs: Path
    promoted: Path
    latest: Path

    def ensure_dirs(self) -> None:
        """Create all checkpoint directories for this track."""
        for directory in (self.runs, self.promoted, self.latest):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class StatePaths:
    """
    Frozen directory contract for cloud CPU continuous training.

    Tactical context: stable path contracts ensure deterministic checkpoint and
    scenario handling during disconnected or degraded operations.
    """

    state_root: Path = field(default_factory=lambda: Path(os.getenv("S3M_STATE_DIR", "/opt/s3m/state/")))
    data_root: Path = field(default_factory=lambda: Path(os.getenv("S3M_DATA_DIR", "/opt/s3m/data/")))

    checkpoints_root: Path = field(init=False)
    manifests_dir: Path = field(init=False)
    metrics_dir: Path = field(init=False)
    journal_dir: Path = field(init=False)
    locks_dir: Path = field(init=False)

    scenarios_root: Path = field(init=False)
    saudi_mod_scenarios_dir: Path = field(init=False)
    ukraine_mod_scenarios_dir: Path = field(init=False)
    nato_scenarios_dir: Path = field(init=False)
    shared_scenarios_dir: Path = field(init=False)
    inbox_dir: Path = field(init=False)
    processed_dir: Path = field(init=False)
    rejected_dir: Path = field(init=False)
    evals_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        state_root = self.state_root
        data_root = self.data_root

        object.__setattr__(self, "checkpoints_root", state_root / "checkpoints")
        object.__setattr__(self, "manifests_dir", state_root / "manifests")
        object.__setattr__(self, "metrics_dir", state_root / "metrics")
        object.__setattr__(self, "journal_dir", state_root / "journal")
        object.__setattr__(self, "locks_dir", state_root / "locks")

        scenarios_root = data_root / "scenarios"
        object.__setattr__(self, "scenarios_root", scenarios_root)
        object.__setattr__(self, "saudi_mod_scenarios_dir", scenarios_root / TrainingTrack.SAUDI_MOD.value)
        object.__setattr__(self, "ukraine_mod_scenarios_dir", scenarios_root / TrainingTrack.UKRAINE_MOD.value)
        object.__setattr__(self, "nato_scenarios_dir", scenarios_root / TrainingTrack.NATO.value)
        object.__setattr__(self, "shared_scenarios_dir", scenarios_root / TrainingTrack.SHARED.value)

        object.__setattr__(self, "inbox_dir", data_root / "inbox")
        object.__setattr__(self, "processed_dir", data_root / "processed")
        object.__setattr__(self, "rejected_dir", data_root / "rejected")
        object.__setattr__(self, "evals_dir", data_root / "evals")

    def for_track(self, track: TrainingTrack) -> TrackCheckpointPaths:
        """Return track-specific checkpoint directory paths."""
        base = self.checkpoints_root / track.value
        return TrackCheckpointPaths(
            runs=base / "runs",
            promoted=base / "promoted",
            latest=base / "latest",
        )

    def scenario_dir(self, track: TrainingTrack) -> Path:
        """Return scenario directory for one training track."""
        return self.scenarios_root / track.value

    def ensure_dirs(self) -> None:
        """Create all configured state and data directories."""
        for directory in (
            self.state_root,
            self.checkpoints_root,
            self.manifests_dir,
            self.metrics_dir,
            self.journal_dir,
            self.locks_dir,
            self.data_root,
            self.scenarios_root,
            self.saudi_mod_scenarios_dir,
            self.ukraine_mod_scenarios_dir,
            self.nato_scenarios_dir,
            self.shared_scenarios_dir,
            self.inbox_dir,
            self.processed_dir,
            self.rejected_dir,
            self.evals_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        for track in TrainingTrack:
            self.for_track(track).ensure_dirs()
