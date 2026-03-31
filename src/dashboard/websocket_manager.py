"""WebSocket connection manager for dashboard live events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Set


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WebSocketManager:
    """Maintain active websocket clients for tactical event broadcasting."""

    def __init__(self) -> None:
        self._connections: Set[Any] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: Any) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: Any) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def send_to(self, websocket: Any, event_type: str, data: Dict[str, Any]) -> None:
        message = {"type": event_type, "data": data, "timestamp": _utcnow()}
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        message = {"type": event_type, "data": data, "timestamp": _utcnow()}
        async with self._lock:
            targets = list(self._connections)
        if not targets:
            return
        await asyncio.gather(*(self._send_or_disconnect(ws, message) for ws in targets), return_exceptions=True)

    async def _send_or_disconnect(self, websocket: Any, message: Dict[str, Any]) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)

    def get_connection_count(self) -> int:
        return len(self._connections)
