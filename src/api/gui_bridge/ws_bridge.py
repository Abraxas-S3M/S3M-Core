"""WebSocket bridge: translates backend events to the GUI envelope format.

The GUI expects:
  { type: "backend.snapshot" | "decision.updated" | "backend.heartbeat" | "backend.error",
    payload: {...},
    timestamp: "ISO-8601" }

The existing backend WS at /dashboard/ws uses:
  { type: "metrics_update" | "alert",
    data: {...},
    timestamp: "ISO-8601" }

This bridge provides the /ws endpoint with the GUI's expected format.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter(tags=["GUI WebSocket"])


class GUIWebSocketBridge:
    """Manage GUI WebSocket clients with heartbeat and event dispatch."""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._heartbeat_task = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
            if self._heartbeat_task is None or self._heartbeat_task.done():
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]) -> None:
        envelope = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        msg = json.dumps(envelope)
        async with self._lock:
            targets = list(self._clients)
        for ws in targets:
            try:
                await ws.send_text(msg)
            except Exception:
                await self.disconnect(ws)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            async with self._lock:
                if not self._clients:
                    break
            await self.broadcast("backend.heartbeat", {"status": "ok"})


# Global bridge instance — importable by adapters to push events
gui_ws_bridge = GUIWebSocketBridge()


@ws_router.websocket("/ws")
async def gui_websocket_endpoint(websocket: WebSocket) -> None:
    await gui_ws_bridge.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            # Client-to-server messages can be handled here if needed
            try:
                msg = json.loads(raw)
                # Future: handle client commands (subscribe to specific topics, etc.)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await gui_ws_bridge.disconnect(websocket)
    except Exception:
        await gui_ws_bridge.disconnect(websocket)


async def emit_to_gui(event_type: str, payload: Dict[str, Any]) -> None:
    """Utility for any adapter/service to push real-time events to GUI clients.

    Valid event_type values:
    - "backend.snapshot"     → full operational state refresh
    - "decision.updated"    → single decision status change
    - "backend.heartbeat"   → keep-alive (auto-managed)
    - "backend.error"       → error notification
    """
    await gui_ws_bridge.broadcast(event_type, payload)
