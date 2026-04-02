"""Blue-force and mission-entity awareness tracker for tactical C2 views."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


class ForceAwarenessManager:
    """Maintain validated force tracks for tactical operator awareness."""

    def __init__(self) -> None:
        self._tracks: Dict[str, Dict[str, Any]] = {}

    def ingest_tracks(self, tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(tracks, list):
            raise ValueError("tracks must be a list")
        accepted = 0
        for raw in tracks:
            if not isinstance(raw, dict):
                continue
            unit_id = str(raw.get("unit_id", "")).strip()
            if not unit_id:
                continue
            position = raw.get("position", [0.0, 0.0, 0.0])
            if not isinstance(position, (list, tuple)) or len(position) != 3:
                continue
            self._tracks[unit_id] = {
                "unit_id": unit_id,
                "role": str(raw.get("role", "unknown")),
                "status": str(raw.get("status", "active")),
                "position": [float(position[0]), float(position[1]), float(position[2])],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            accepted += 1
        return {
            "accepted": accepted,
            "track_count": len(self._tracks),
            "tracks": list(self._tracks.values()),
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "component": "force_awareness_manager",
            "track_count": len(self._tracks),
        }

