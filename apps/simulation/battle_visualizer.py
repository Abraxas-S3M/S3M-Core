"""Battle replay frame generation for dashboards and offline playback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from apps.simulation.models import WargameResult, WargameSession, WargameTurn


class BattleVisualizer:
    """Transforms turn data into 2D tactical visualization frame structures."""

    def __init__(self):
        self._sessions: Dict[str, WargameSession] = {}

    def register_session(self, session: WargameSession) -> None:
        self._sessions[session.session_id] = session

    def _icon_for(self, unit_type: str, allegiance: str) -> str:
        base = "blue" if allegiance == "blue" else "red"
        kind = str(unit_type).lower()
        if "armor" in kind:
            return f"{base}_armor"
        if "air" in kind:
            return f"{base}_air"
        if "ship" in kind or "naval" in kind:
            return f"{base}_naval"
        return f"{base}_infantry"

    def generate_turn_frame(self, turn: WargameTurn, bounds: dict) -> dict:
        units = []
        for unit in turn.state_snapshot.get("units", []):
            x, y = unit.get("position", (0.0, 0.0))
            units.append(
                {
                    "id": unit.get("unit_id"),
                    "allegiance": unit.get("allegiance"),
                    "type": unit.get("type", "infantry"),
                    "x": float(x),
                    "y": float(y),
                    "health_pct": round(float(unit.get("health", 1.0)) * 100.0, 2),
                    "status": "active" if unit.get("health", 0) > 0 else "destroyed",
                    "icon": self._icon_for(unit.get("type", "infantry"), unit.get("allegiance", "blue")),
                }
            )

        engagements: List[dict] = []
        movements: List[dict] = []
        detections: List[dict] = []
        for event in turn.events:
            if event.get("type") == "engagement":
                engagements.append(
                    {
                        "attacker": event.get("attacker"),
                        "defender": event.get("defender"),
                        "position": event.get("position", (0.0, 0.0)),
                        "result": event.get("result"),
                    }
                )
            elif event.get("type") == "movement":
                movements.append(
                    {
                        "unit_id": event.get("unit_id"),
                        "from": event.get("from"),
                        "to": event.get("to"),
                    }
                )
            elif event.get("type") == "detection":
                detections.append(
                    {
                        "detector": event.get("detector"),
                        "target": event.get("target"),
                        "confidence": event.get("confidence", 0.5),
                    }
                )

        return {
            "turn": turn.turn_number,
            "units": units,
            "engagements": engagements,
            "movements": movements,
            "detections": detections,
            "terrain_features": turn.state_snapshot.get("terrain_features", []),
            "bounds": bounds,
        }

    def generate_replay(self, session: WargameSession) -> List[dict]:
        bounds = session.config.parameters.get("bounds", {"min_x": 0, "min_y": 0, "max_x": 200, "max_y": 200})
        return [self.generate_turn_frame(turn, bounds=bounds) for turn in session.turns]

    def generate_summary_map(self, result: WargameResult, session: WargameSession) -> dict:
        traces: Dict[str, List[tuple]] = {}
        engagements: List[dict] = []
        for turn in session.turns:
            for unit in turn.state_snapshot.get("units", []):
                traces.setdefault(unit.get("unit_id"), []).append(unit.get("position", (0.0, 0.0)))
            for event in turn.events:
                if event.get("type") == "engagement":
                    engagements.append({"turn": turn.turn_number, "position": event.get("position", (0.0, 0.0))})
        final_positions = (
            {u.get("unit_id"): u.get("position", (0.0, 0.0)) for u in session.turns[-1].state_snapshot.get("units", [])}
            if session.turns
            else {}
        )
        return {
            "wargame_id": result.wargame_id,
            "outcome": result.outcome,
            "final_positions": final_positions,
            "movement_traces": traces,
            "engagement_markers": engagements,
        }

    def export_replay(self, session_id: str, filepath: str):
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("session not registered")
        replay = self.generate_replay(session)
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(replay, indent=2), encoding="utf-8")
