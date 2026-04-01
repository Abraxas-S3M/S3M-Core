"""Tactical mesh adapter for resilient edge relay in coalition exercises."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


class TacticalMeshAdapter:
    """Lightweight mesh abstraction for local/offline exercise networking."""

    def __init__(self):
        self.connected = False
        self.nodes: Dict[str, dict] = {}
        self.messages: List[dict] = []

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def register_node(self, node_id: str, metadata: dict = None) -> dict:
        self.nodes[node_id] = {"node_id": node_id, "metadata": dict(metadata or {})}
        return self.nodes[node_id]

    def relay(self, source: str, destination: str, payload: Any) -> bool:
        if not self.connected:
            return False
        self.messages.append(
            {
                "source": source,
                "destination": destination,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return True

    def health_check(self) -> dict:
        return {
            "status": "operational" if self.connected else "offline",
            "nodes": len(self.nodes),
            "messages": len(self.messages),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

