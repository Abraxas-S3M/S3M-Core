"""API endpoints for cloud CPU training status, metrics, and control.

These endpoints read from the shared filesystem (JSONL metrics, manifests).
Control commands (pause/resume) use file-based IPC via state/locks/.
No shared memory with the trainer process.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.training.cloud_cpu.metrics_store import MetricsStore
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack

cloud_training_router = APIRouter(prefix="/api/v1/training")

_paths = StatePaths()
_metrics = MetricsStore(_paths.metrics)
_CHECKPOINT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@cloud_training_router.get("/status")
async def training_status() -> Dict[str, Any]:
    """Overall training status across all domain tracks."""
    tracks_status = {}
    for track in TrainingTrack:
        tracks_status[track.value] = _metrics.get_track_summary(track.value)

    # Lock files indicate trainer workers that are active per tactical track.
    trainer_alive = any((_paths.locks / f"{track.value}.lock").exists() for track in TrainingTrack)
    return {
        "trainer_alive": trainer_alive,
        "deployment_mode": "cloud_cpu_demo",
        "tracks": tracks_status,
    }


@cloud_training_router.get("/metrics")
async def training_metrics(
    track: str = Query(..., description="Training track name"),
    n: int = Query(default=100, ge=1, le=1000),
) -> Dict[str, Any]:
    """Cycle-level training metrics for a specific track."""
    _validate_track(track)
    return {
        "track": track,
        "metrics": _metrics.get_latest(track, n),
    }


@cloud_training_router.get("/checkpoints")
async def training_checkpoints(
    track: str = Query(..., description="Training track name"),
) -> Dict[str, Any]:
    """List checkpoints for a track (runs and promoted)."""
    _validate_track(track)
    track_enum = TrainingTrack(track)
    tp = _paths.for_track(track_enum)

    runs = _list_checkpoint_manifests(tp.runs)
    promoted = _list_checkpoint_manifests(tp.promoted)
    return {
        "track": track,
        "runs": runs,
        "promoted": promoted,
        "latest_promoted": promoted[-1] if promoted else None,
    }


@cloud_training_router.post("/pause")
async def training_pause(
    track: Optional[str] = Query(default=None, description="Optional track to pause. If omitted pauses all."),
) -> Dict[str, Any]:
    """Write a pause command file for the trainer to pick up."""
    targets = _resolve_targets(track)
    for t in targets:
        cmd_path = _paths.locks / f"{t.value}.pause"
        cmd_path.touch()
    return {"status": "pause_requested", "tracks": [t.value for t in targets]}


@cloud_training_router.post("/resume")
async def training_resume(
    track: Optional[str] = Query(default=None, description="Optional track to resume. If omitted resumes all."),
) -> Dict[str, Any]:
    """Remove pause command file to resume training."""
    targets = _resolve_targets(track)
    for t in targets:
        cmd_path = _paths.locks / f"{t.value}.pause"
        cmd_path.unlink(missing_ok=True)
    return {"status": "resume_requested", "tracks": [t.value for t in targets]}


@cloud_training_router.post("/promote")
async def training_promote(
    track: str = Query(..., description="Training track name"),
    checkpoint: str = Query(..., description="Checkpoint directory name under runs/"),
) -> Dict[str, Any]:
    """Manually promote a checkpoint from runs/ to promoted/."""
    _validate_track(track)
    checkpoint_name = _validate_checkpoint_name(checkpoint)
    tp = _paths.for_track(TrainingTrack(track))

    source_dir = tp.runs / checkpoint_name
    if not source_dir.exists() or not source_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {checkpoint_name}")

    manifest_path = source_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=400, detail=f"Checkpoint missing manifest: {checkpoint_name}")

    target_dir = tp.promoted / checkpoint_name
    try:
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to promote checkpoint: {exc}") from exc

    return {
        "status": "promoted",
        "track": track,
        "checkpoint": checkpoint_name,
        "source": str(source_dir),
        "target": str(target_dir),
    }


@cloud_training_router.get("/tracks")
async def training_tracks() -> Dict[str, Any]:
    """List all training tracks with summaries."""
    tracks = {}
    for track in TrainingTrack:
        tracks[track.value] = {
            "summary": _metrics.get_track_summary(track.value),
            "kpis": _metrics.get_demo_kpis(track.value),
        }
    return {"tracks": tracks}


@cloud_training_router.get("/kpis")
async def training_kpis(
    track: str = Query(..., description="Training track name"),
) -> Dict[str, Any]:
    """Demo-ready KPIs for leadership dashboards."""
    _validate_track(track)
    return _metrics.get_demo_kpis(track)


def _resolve_targets(track: Optional[str]) -> List[TrainingTrack]:
    if track is None:
        return list(TrainingTrack)
    _validate_track(track)
    return [TrainingTrack(track)]


def _validate_track(track: str) -> None:
    valid = {t.value for t in TrainingTrack}
    if track not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown track: {track}. Valid: {sorted(valid)}")


def _validate_checkpoint_name(checkpoint: str) -> str:
    name = checkpoint.strip()
    if not name or Path(name).name != name or not _CHECKPOINT_NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Invalid checkpoint name")
    return name


def _list_checkpoint_manifests(directory: Path) -> List[Dict[str, Any]]:
    if not directory.exists():
        return []

    manifests: List[Dict[str, Any]] = []
    for ckpt_dir in sorted(directory.iterdir()):
        if not ckpt_dir.is_dir():
            continue
        manifest_path = ckpt_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                manifests.append(payload)
        except (json.JSONDecodeError, OSError):
            continue
    return manifests
