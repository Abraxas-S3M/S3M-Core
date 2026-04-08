"""COP (Common Operating Picture) adapter.

Merges sensor-fused tracks from COPDataProvider and threat events from
ThreatDashProvider into the unified GUIThreatTrack shape.

Internal dependencies:
- src.dashboard.providers.cop_provider.COPDataProvider (get_tracks, get_threats)
- src.dashboard.providers.threat_dash_provider.ThreatDashProvider (get_threat_feed)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.api.gui_bridge.models.gui_schemas import (
    GUIMissionLayer,
    GUIReplayFrame,
    GUIThreatTrack,
    GUITracksData,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class COPAdapter:
    def __init__(self):
        from src.dashboard.providers.cop_provider import COPDataProvider
        self._cop = COPDataProvider()

    def get_tracks(self) -> GUITracksData:
        raw_tracks = self._cop.get_tracks()
        gui_tracks = []
        for t in raw_tracks:
            gui_tracks.append(GUIThreatTrack(
                id=t.get("id", "UNKNOWN"),
                domain=self._infer_domain(t),
                confidence=self._to_percent(t.get("confidence", 0)),
                severity=self._to_percent(t.get("threat_score", t.get("confidence", 0))),
                correlatedTrackIds=list(t.get("correlated", [])),
                summary=t.get("classification", t.get("type", "Unknown track")),
                lastSeen=t.get("last_update", _now_iso()),
            ))
        return GUITracksData(tracks=gui_tracks, updatedAt=_now_iso())

    def get_threat_tracks(self) -> GUITracksData:
        """Threat-specific tracks from the threat dashboard provider."""
        raw_threats = self._cop.get_threats()
        gui_tracks = []
        for t in raw_threats:
            level = t.get("level", "MEDIUM")
            severity_map = {"CRITICAL": 95, "HIGH": 75, "MEDIUM": 50, "LOW": 25, "INFO": 10}
            gui_tracks.append(GUIThreatTrack(
                id=t.get("id", "UNKNOWN"),
                domain=t.get("category", "kinetic").lower(),
                confidence=self._to_percent(t.get("confidence", 0.5)),
                severity=severity_map.get(level, 50),
                correlatedTrackIds=[],
                summary=t.get("description", t.get("title", "")),
                lastSeen=t.get("timestamp", _now_iso()),
            ))
        return GUITracksData(tracks=gui_tracks, updatedAt=_now_iso())

    def get_replay(self, start_time: str, end_time: str) -> List[dict]:
        """Return replay frames within a commander-selected time window."""
        try:
            start_dt = self._parse_iso_timestamp(start_time)
            end_dt = self._parse_iso_timestamp(end_time)
        except ValueError:
            return []
        if start_dt > end_dt:
            return []

        # Tactical context: GUI replay follows validation harness artifacts
        # so operators can scrub deterministic mission timeline events offline.
        try:
            from src.validation.replay_harness import ReplayHarness
        except ImportError:
            ReplayHarness = None  # pragma: no cover - compatibility fallback
        _ = ReplayHarness

        try:
            from src.simulation.adapters.replay_recorder import ReplayRecorder
        except Exception:
            return []

        replay_frames: List[dict] = []
        recorder = ReplayRecorder()
        for artifact in recorder.list_replays():
            created_at = artifact.created_at
            if not (start_dt <= created_at <= end_dt):
                continue
            try:
                for state in recorder.load_replay(artifact.replay_id):
                    frame_time = state.timestamp
                    if not (start_dt <= frame_time <= end_dt):
                        continue
                    frame = GUIReplayFrame(
                        timestamp=frame_time.isoformat(),
                        tracks=self._tracks_from_sim_state(state.to_dict()),
                    )
                    replay_frames.append(self._dump_model(frame))
            except Exception:
                continue
        return replay_frames

    def get_mission_overlay(self, mission_id: Optional[str] = None) -> dict:
        """Return tactical mission overlay including waypoints and objectives."""
        if mission_id is not None and not isinstance(mission_id, str):
            return self._dump_model(GUIMissionLayer(
                missionId="",
                waypoints=[],
                phaseLines=[],
                objectives=[],
            ))

        try:
            from src.planning.mission_planner import MissionPlanner
        except ImportError:
            from src.planning.mission_planner import (
                MultiDomainMissionPlanner as MissionPlanner,
            )

        mission_plan = self._select_mission_plan(MissionPlanner(), mission_id=mission_id)
        if not mission_plan:
            return self._dump_model(GUIMissionLayer(
                missionId=mission_id or "none",
                waypoints=[],
                phaseLines=[],
                objectives=[],
            ))

        waypoints = self._normalize_waypoints(mission_plan.get("waypoints", []))
        objectives = self._extract_objectives(mission_plan)
        phase_lines = self._build_phase_lines(waypoints)
        return self._dump_model(GUIMissionLayer(
            missionId=str(mission_plan.get("mission_id", mission_id or "unknown")),
            waypoints=waypoints,
            phaseLines=phase_lines,
            objectives=objectives,
        ))

    @staticmethod
    def _infer_domain(track: dict) -> str:
        track_type = str(track.get("type", "")).lower()
        if any(kw in track_type for kw in ("air", "uav", "aircraft", "missile")):
            return "kinetic"
        if any(kw in track_type for kw in ("cyber", "network", "packet")):
            return "cyber"
        if any(kw in track_type for kw in ("sigint", "elint", "humint")):
            return "intel"
        return "kinetic"

    @classmethod
    def _tracks_from_sim_state(cls, state_payload: Dict[str, Any]) -> List[GUIThreatTrack]:
        tracks: List[GUIThreatTrack] = []
        for raw_entity in state_payload.get("entities", []):
            if not isinstance(raw_entity, dict):
                continue
            entity_type = str(raw_entity.get("entity_type", "UNKNOWN"))
            if not entity_type.startswith("ENEMY_"):
                continue
            confidence = cls._to_percent(raw_entity.get("health", 0.5))
            metadata = raw_entity.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            tracks.append(
                GUIThreatTrack(
                    id=str(raw_entity.get("entity_id", "UNKNOWN")),
                    domain=cls._infer_domain({"type": entity_type}),
                    confidence=confidence,
                    severity=confidence,
                    correlatedTrackIds=list(metadata.get("correlatedTrackIds", [])),
                    summary=entity_type,
                    lastSeen=str(state_payload.get("timestamp", _now_iso())),
                )
            )
        return tracks

    @staticmethod
    def _parse_iso_timestamp(raw_value: str) -> datetime:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("timestamp must be a non-empty string")
        normalized = raw_value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _select_mission_plan(planner: Any, mission_id: Optional[str]) -> Dict[str, Any]:
        list_missions = getattr(planner, "list_missions", None)
        if callable(list_missions):
            missions = list_missions() or []
        else:
            get_missions = getattr(planner, "get_missions", None)
            missions = get_missions() if callable(get_missions) else []
        if not isinstance(missions, list):
            return {}
        if mission_id:
            for item in missions:
                if isinstance(item, dict) and str(item.get("mission_id")) == mission_id:
                    return item
            return {}
        for item in missions:
            if isinstance(item, dict):
                return item
        return {}

    @staticmethod
    def _normalize_waypoints(raw_waypoints: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_waypoints, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for idx, point in enumerate(raw_waypoints):
            if isinstance(point, dict):
                x = float(point.get("x", 0.0))
                y = float(point.get("y", 0.0))
                z = float(point.get("z", point.get("alt", 0.0)))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                x = float(point[0])
                y = float(point[1])
                z = float(point[2]) if len(point) > 2 else 0.0
            else:
                continue
            normalized.append({"id": f"WP-{idx + 1}", "x": x, "y": y, "z": z})
        return normalized

    @staticmethod
    def _build_phase_lines(waypoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        for idx in range(1, len(waypoints)):
            lines.append(
                {
                    "id": f"PHASE-LINE-{idx}",
                    "from": waypoints[idx - 1]["id"],
                    "to": waypoints[idx]["id"],
                }
            )
        return lines

    @staticmethod
    def _extract_objectives(mission_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_objectives = mission_plan.get("objectives", [])
        if isinstance(raw_objectives, list) and raw_objectives:
            objectives: List[Dict[str, Any]] = []
            for idx, objective in enumerate(raw_objectives):
                if isinstance(objective, dict):
                    objectives.append(
                        {
                            "id": str(objective.get("id", f"OBJ-{idx + 1}")),
                            "label": str(objective.get("label", objective.get("name", "Objective"))),
                            "status": str(objective.get("status", "planned")),
                        }
                    )
                else:
                    objectives.append(
                        {
                            "id": f"OBJ-{idx + 1}",
                            "label": str(objective),
                            "status": "planned",
                        }
                    )
            return objectives
        mission_type = str(mission_plan.get("mission_type", "mission")).lower()
        return [
            {
                "id": "OBJ-1",
                "label": f"{mission_type}-objective",
                "status": str(mission_plan.get("status", "planned")),
            }
        ]

    @staticmethod
    def _dump_model(model: Any) -> dict:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return dict(getattr(model, "__dict__", {}))

    @staticmethod
    def _to_percent(val) -> int:
        v = float(val) if val else 0
        if v < 0:
            return 0
        if v <= 1.0:
            return int(v * 100)
        return int(min(100, max(0, v)))
