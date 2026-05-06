"""FastAPI routes for Common Operational Picture (COP) backend data."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from src.cop.cop_models import CopState
from src.cop.cop_service import CopService

router = APIRouter(tags=["COP"])
cop_service = CopService()


def _track_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/api/cop/{track}/state", response_model=CopState)
async def cop_state(track: str) -> CopState:
    try:
        return await cop_service.get_state(track)
    except ValueError as exc:
        raise _track_error(exc) from exc


@router.get("/api/cop/{track}/map")
async def cop_map(track: str) -> Dict[str, Any]:
    try:
        return await cop_service.get_map(track)
    except ValueError as exc:
        raise _track_error(exc) from exc


@router.get("/api/cop/{track}/tracks")
async def cop_tracks(track: str) -> Dict[str, Any]:
    try:
        return await cop_service.get_tracks(track)
    except ValueError as exc:
        raise _track_error(exc) from exc


@router.get("/api/cop/{track}/alerts")
async def cop_alerts(track: str) -> Dict[str, Any]:
    try:
        return await cop_service.get_alerts(track)
    except ValueError as exc:
        raise _track_error(exc) from exc


@router.get("/api/cop/{track}/decisions")
async def cop_decisions(track: str) -> Dict[str, Any]:
    try:
        return await cop_service.get_decisions(track)
    except ValueError as exc:
        raise _track_error(exc) from exc


@router.get("/api/cop/{track}/feed")
async def cop_feed(track: str) -> Dict[str, Any]:
    try:
        return await cop_service.get_feed(track)
    except ValueError as exc:
        raise _track_error(exc) from exc


@router.websocket("/ws/cop/{track}")
async def cop_ws_endpoint(websocket: WebSocket, track: str) -> None:
    try:
        normalized_track = cop_service.validate_track(track)
    except ValueError:
        await websocket.close(code=1008, reason="Unsupported COP track")
        return

    await websocket.accept()
    initial_state = await cop_service.get_state(normalized_track)
    await websocket.send_json({"type": "cop_update", "state": initial_state.model_dump()})

    sequence = 0
    try:
        while True:
            await asyncio.sleep(cop_service.websocket_delay_seconds(normalized_track, sequence))
            events = await cop_service.build_websocket_events(normalized_track, sequence)
            for event in events:
                await websocket.send_json(event)
            sequence += 1
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011, reason="COP stream error")
