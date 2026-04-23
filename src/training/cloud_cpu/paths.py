"""Filesystem layout helpers for cloud CPU training state.

Military/tactical context:
Track-isolated directories limit blast radius if one adaptation stream is
corrupted or compromised during disconnected, contested operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict


class TrainingTrack(str, Enum):
    """Supported adaptation tracks."""

    SAUDI_MOD = "saudi_mod"
    UKRAINE_MOD = "ukraine_mod"
    NATO = "nato"
    INDOPAC_MOD = "indopac_mod"
    SOUTHAM_MOD = "southam_mod"
    AFRICA_MOD = "africa_mod"
    SHARED = "shared"


@dataclass(frozen=True)
class TrackPaths:
    """Per-track directory bundle."""

    root: Path
    scenarios: Path
    runs: Path
    promoted: Path
    processed: Path
    rejected: Path


class StatePaths:
    """Computes and materializes cloud CPU training directories."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.inbox = self.root / "inbox"
        self.rejected = self.root / "rejected"
        self.processed = self.root / "processed"
        self.tracks_root = self.root / "tracks"
        self.metrics = self.root / "metrics"
        self.locks = self.root / "locks"
        self._track_paths: Dict[TrainingTrack, TrackPaths] = {}

        self._ensure_dir(self.root)
        self._ensure_dir(self.inbox)
        self._ensure_dir(self.rejected)
        self._ensure_dir(self.processed)
        self._ensure_dir(self.tracks_root)
        self._ensure_dir(self.metrics)
        self._ensure_dir(self.locks)

        for track in TrainingTrack:
            track_root = self.tracks_root / track.value
            paths = TrackPaths(
                root=track_root,
                scenarios=track_root / "scenarios",
                runs=track_root / "checkpoints" / "runs",
                promoted=track_root / "checkpoints" / "promoted",
                processed=self.processed / track.value,
                rejected=self.rejected / track.value,
            )
            self._track_paths[track] = paths
            self._ensure_dir(paths.root)
            self._ensure_dir(paths.scenarios)
            self._ensure_dir(paths.runs)
            self._ensure_dir(paths.promoted)
            self._ensure_dir(paths.processed)
            self._ensure_dir(paths.rejected)

    def ensure_dirs(self) -> None:
        """Re-ensure all directories exist (idempotent)."""
        for d in [self.root, self.inbox, self.rejected, self.processed, self.tracks_root, self.metrics, self.locks]:
            self._ensure_dir(d)
        for track in self._track_paths.values():
            for d in [track.root, track.scenarios, track.runs, track.promoted, track.processed, track.rejected]:
                self._ensure_dir(d)

    def for_track(self, track: TrainingTrack) -> TrackPaths:
        if not isinstance(track, TrainingTrack):
            track = TrainingTrack(str(track))
        return self._track_paths[track]

    def scenario_dir(self, track: TrainingTrack) -> Path:
        return self.for_track(track).scenarios

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

