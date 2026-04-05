"""Mission executive API routes for lifecycle and manual tactical ticking."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.api.platform_routes import PlatformRegistry, platform_registry
from src.autonomy.mission_executive import MissionExecutive
from src.platforms.common.messages import MissionTask, MissionTaskType, MobilityCommandType


mission_router = APIRouter(prefix="/api/missions")


class MissionTaskRequest(BaseModel):
    """Mission task payload accepted by mission lifecycle endpoints."""

    task_type: MissionTaskType
    waypoints: list[tuple[float, float, float]] = Field(default_factory=list, min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    assigned_platform: str = Field(..., min_length=1)

    @field_validator("waypoints", mode="before")
    @classmethod
    def _normalize_waypoints(cls, value: Any) -> list[tuple[float, float, float]]:
        if not isinstance(value, list):
            raise ValueError("waypoints must be a list")
        normalized: list[tuple[float, float, float]] = []
        for waypoint in value:
            if not isinstance(waypoint, (list, tuple)) or len(waypoint) != 3:
                raise ValueError("each waypoint must be [x, y, z]")
            normalized.append((float(waypoint[0]), float(waypoint[1]), float(waypoint[2])))
        return normalized


class _MissionRuntime:
    """Container for shared mission executive state across API requests."""

    def __init__(self, registry: PlatformRegistry) -> None:
        self.registry = registry
        self._lock = RLock()
        self.executive = MissionExecutive()
        self.assigned_platform_id: str | None = None
        self.parameters: dict[str, Any] = {}

    def reset_assignment(self) -> None:
        self.assigned_platform_id = None
        self.parameters = {}


runtime = _MissionRuntime(platform_registry)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _json_compatible(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def _resolve_assigned_adapter() -> Any:
    if not runtime.assigned_platform_id:
        raise HTTPException(status_code=400, detail="No assigned platform. Start a mission first.")
    adapter = runtime.registry.get_platform(runtime.assigned_platform_id)
    if adapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Assigned platform not found: {runtime.assigned_platform_id}",
        )
    return adapter


def _apply_mobility_commands(adapter: Any, commands: list[Any]) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for command in commands:
        command_type = getattr(command, "command_type", None)
        if command_type != MobilityCommandType.MOVE_TO:
            continue
        target = getattr(command, "target_position", None)
        if target is None:
            continue

        if hasattr(adapter, "apply_mobility_command"):
            adapter.apply_mobility_command(command)
        elif hasattr(adapter, "set_target_position"):
            adapter.set_target_position(target)
        elif hasattr(adapter, "_position"):
            # Tactical simulation adapters store local position directly to
            # emulate immediate maneuver updates in offline validation runs.
            adapter._position = (float(target[0]), float(target[1]), float(target[2]))

        applied.append(
            {
                "command_type": "move_to",
                "target_position": [float(target[0]), float(target[1]), float(target[2])],
            }
        )
    return applied


@mission_router.post("/start")
async def start_mission(payload: MissionTaskRequest) -> dict[str, Any]:
    """Start a mission on an assigned platform adapter."""
    adapter = runtime.registry.get_platform(payload.assigned_platform)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Unknown assigned_platform: {payload.assigned_platform}")

    task = MissionTask(
        task_type=payload.task_type,
        waypoints=payload.waypoints,
        parameters=payload.parameters,
        assigned_platform=payload.assigned_platform,
    )

    with runtime._lock:
        started = runtime.executive.start_mission(task)
        if not started:
            raise HTTPException(status_code=422, detail="MissionExecutive rejected mission task")
        runtime.assigned_platform_id = payload.assigned_platform
        runtime.parameters = dict(payload.parameters)

    return {
        "status": "started",
        "assigned_platform": payload.assigned_platform,
        "phase": runtime.executive.phase,
        "task": _json_compatible(task),
        "platform_state": _json_compatible(adapter.read_state()),
    }


@mission_router.post("/pause")
async def pause_mission() -> dict[str, Any]:
    """Pause the active mission lifecycle."""
    with runtime._lock:
        if not runtime.executive.pause():
            raise HTTPException(status_code=400, detail="No active mission to pause")
    return {"status": "paused", "phase": runtime.executive.phase}


@mission_router.post("/resume")
async def resume_mission() -> dict[str, Any]:
    """Resume a paused mission lifecycle."""
    with runtime._lock:
        if not runtime.executive.resume():
            raise HTTPException(status_code=400, detail="No paused mission to resume")
    return {"status": "resumed", "phase": runtime.executive.phase}


@mission_router.post("/abort")
async def abort_mission() -> dict[str, Any]:
    """Abort the active mission lifecycle."""
    with runtime._lock:
        if not runtime.executive.abort():
            raise HTTPException(status_code=400, detail="No active mission to abort")
        runtime.reset_assignment()
    return {"status": "aborted", "phase": runtime.executive.phase}


@mission_router.get("/status")
async def mission_status() -> dict[str, Any]:
    """Get mission runtime state including lifecycle phase."""
    return {
        "is_active": runtime.executive.is_active,
        "is_paused": runtime.executive.is_paused,
        "phase": runtime.executive.phase,
        "assigned_platform": runtime.assigned_platform_id,
        "current_task": _json_compatible(runtime.executive.current_task),
    }


@mission_router.get("/phase-log")
async def mission_phase_log() -> dict[str, Any]:
    """Return mission executive phase transition history."""
    log = runtime.executive.phase_log
    return {"total": len(log), "entries": _json_compatible(log)}


@mission_router.post("/tick")
async def tick_mission() -> dict[str, Any]:
    """Manually tick mission executive, feed tracks, and apply generated commands."""
    adapter = _resolve_assigned_adapter()
    platform_state = adapter.read_state()
    track_store = runtime.registry.get_track_store()
    tracks = track_store.get_tracks()

    mobility_commands, sensor_commands = runtime.executive.tick(platform_state=platform_state, tracks=tracks)
    applied_commands = _apply_mobility_commands(adapter, mobility_commands)

    return {
        "phase": runtime.executive.phase,
        "platform_state": _json_compatible(platform_state),
        "tracks": _json_compatible(tracks),
        "mobility_commands": _json_compatible(mobility_commands),
        "sensor_commands": _json_compatible(sensor_commands),
        "applied_commands": applied_commands,
    }
