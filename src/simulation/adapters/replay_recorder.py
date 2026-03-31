"""Replay recorder for streaming simulation snapshots to JSONL artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional
from uuid import uuid4
import json
import os

from src.simulation.models import EntityType, ReplayArtifact, SimEntity, SimulationState


class ReplayRecorder:
    """Records tactical simulation runs for reproducible after-action analysis."""

    def __init__(self, output_dir: str = "data/replays/"):
        if not isinstance(output_dir, str) or not output_dir.strip():
            raise ValueError("output_dir must be a non-empty string")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._max_size_bytes = 500 * 1024 * 1024

        self._active_handle = None
        self._active_path: Optional[Path] = None
        self._active_replay_id: Optional[str] = None
        self._active_scenario_id: Optional[str] = None
        self._active_simulator: Optional[str] = None
        self._created_at: Optional[datetime] = None
        self._tick_count = 0
        self._first_sim_time: Optional[float] = None
        self._last_sim_time: Optional[float] = None
        self._truncated = False

    def _meta_path(self, replay_id: str) -> Path:
        return self.output_dir / f"{replay_id}.meta.json"

    def start_recording(self, simulator_name: str, scenario_id: Optional[str] = None) -> str:
        """Start replay capture and return replay identifier."""
        if self._active_handle is not None:
            self.stop_recording()
        replay_id = str(uuid4())
        replay_path = self.output_dir / f"{replay_id}.jsonl"
        self._active_handle = replay_path.open("w", encoding="utf-8")
        self._active_path = replay_path
        self._active_replay_id = replay_id
        self._active_scenario_id = scenario_id
        self._active_simulator = simulator_name
        self._created_at = datetime.now(timezone.utc)
        self._tick_count = 0
        self._first_sim_time = None
        self._last_sim_time = None
        self._truncated = False
        return replay_id

    def record_tick(self, state: SimulationState):
        """Append one simulation state record to JSONL stream."""
        if self._active_handle is None or self._active_path is None:
            raise RuntimeError("recording not started")
        if not isinstance(state, SimulationState):
            raise ValueError("state must be SimulationState")
        if self._active_path.stat().st_size >= self._max_size_bytes:
            self._truncated = True
            return

        self._active_handle.write(json.dumps(state.to_dict()) + "\n")
        self._active_handle.flush()
        self._tick_count += 1
        if self._first_sim_time is None:
            self._first_sim_time = state.sim_time_seconds
        self._last_sim_time = state.sim_time_seconds

    def stop_recording(self) -> ReplayArtifact:
        """Stop capture, write metadata sidecar, and return replay artifact."""
        if self._active_handle is None or self._active_path is None or self._active_replay_id is None:
            raise RuntimeError("recording not started")

        self._active_handle.flush()
        self._active_handle.close()
        self._active_handle = None

        duration = 0.0
        if self._first_sim_time is not None and self._last_sim_time is not None:
            duration = max(0.0, self._last_sim_time - self._first_sim_time)

        file_size = self._active_path.stat().st_size
        artifact = ReplayArtifact(
            replay_id=self._active_replay_id,
            scenario_id=self._active_scenario_id,
            simulator=self._active_simulator or "unknown",
            created_at=self._created_at or datetime.now(timezone.utc),
            duration_seconds=duration,
            tick_count=self._tick_count,
            filepath=str(self._active_path),
            file_size_bytes=file_size,
            metadata={"truncated": self._truncated, "max_file_size_bytes": self._max_size_bytes},
        )

        with self._meta_path(self._active_replay_id).open("w", encoding="utf-8") as handle:
            json.dump(artifact.to_dict(), handle, indent=2)

        self._active_path = None
        self._active_replay_id = None
        self._active_scenario_id = None
        self._active_simulator = None
        self._created_at = None
        self._tick_count = 0
        self._first_sim_time = None
        self._last_sim_time = None
        self._truncated = False
        return artifact

    def _state_from_dict(self, payload: Dict[str, object]) -> SimulationState:
        entities = []
        for raw_entity in payload.get("entities", []):
            if not isinstance(raw_entity, dict):
                continue
            entities.append(
                SimEntity(
                    entity_id=str(raw_entity.get("entity_id", "unknown")),
                    entity_type=EntityType(str(raw_entity.get("entity_type", EntityType.UNKNOWN.value))),
                    position=tuple(raw_entity.get("position", (0.0, 0.0, 0.0))),
                    velocity=tuple(raw_entity.get("velocity", (0.0, 0.0, 0.0))),
                    heading=float(raw_entity.get("heading", 0.0)),
                    health=float(raw_entity.get("health", 1.0)),
                    active=bool(raw_entity.get("active", True)),
                    metadata=dict(raw_entity.get("metadata", {})),
                )
            )

        return SimulationState(
            timestamp=datetime.fromisoformat(str(payload.get("timestamp"))),
            sim_time_seconds=float(payload.get("sim_time_seconds", 0.0)),
            entities=entities,
            terrain=dict(payload.get("terrain", {})),
            weather=dict(payload.get("weather", {})),
            active_events=list(payload.get("active_events", [])),
            metadata=dict(payload.get("metadata", {})),
        )

    def load_replay(self, replay_id: str) -> Iterator[SimulationState]:
        """Yield replay frames in a streaming fashion to avoid high memory use."""
        replay_path = self.output_dir / f"{replay_id}.jsonl"
        if not replay_path.exists():
            raise FileNotFoundError(f"replay not found: {replay_path}")

        with replay_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield self._state_from_dict(json.loads(line))

    def list_replays(self) -> List[ReplayArtifact]:
        """List all replay artifacts from sidecar metadata files."""
        artifacts: List[ReplayArtifact] = []
        for meta_file in sorted(self.output_dir.glob("*.meta.json")):
            try:
                payload = json.loads(meta_file.read_text(encoding="utf-8"))
                artifacts.append(
                    ReplayArtifact(
                        replay_id=str(payload["replay_id"]),
                        scenario_id=payload.get("scenario_id"),
                        simulator=str(payload["simulator"]),
                        created_at=datetime.fromisoformat(str(payload["created_at"])),
                        duration_seconds=float(payload.get("duration_seconds", 0.0)),
                        tick_count=int(payload.get("tick_count", 0)),
                        filepath=str(payload["filepath"]),
                        file_size_bytes=int(payload.get("file_size_bytes", 0)),
                        metadata=dict(payload.get("metadata", {})),
                    )
                )
            except Exception:
                continue
        return artifacts

    def delete_replay(self, replay_id: str):
        """Delete replay data and metadata sidecar from local storage."""
        replay_path = self.output_dir / f"{replay_id}.jsonl"
        meta_path = self._meta_path(replay_id)
        if replay_path.exists():
            os.remove(replay_path)
        if meta_path.exists():
            os.remove(meta_path)
