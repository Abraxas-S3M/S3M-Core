"""COP (Common Operating Picture) adapter.

Merges sensor-fused tracks from COPDataProvider and threat events from
ThreatDashProvider into the unified GUIThreatTrack shape.

Internal dependencies:
- src.dashboard.providers.cop_provider.COPDataProvider (get_tracks, get_threats)
- src.dashboard.providers.threat_dash_provider.ThreatDashProvider (get_threat_feed)
"""

from datetime import datetime, timezone
from math import atan2, cos, degrees, radians, sqrt
from typing import Any, Dict, List, Optional, Tuple

from src.api.gui_bridge.models.gui_schemas import (
    GUIMissionLayer,
    GUIReplayFrame,
    GUIThreatTrack,
    GUITracksData,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class COPAdapter:
    def __init__(self):
        from src.dashboard.providers.cop_provider import COPDataProvider

        self._cop = COPDataProvider()
        self._store = None
        self._use_store_tracks = False
        self._use_store_threats = False
        try:
            from src.persistence.store_seeder import seed_store_if_empty

            self._store = seed_store_if_empty()
            self._use_store_tracks = self._store.has_data("tracks")
            self._use_store_threats = self._store.has_data("threats")
        except Exception:
            pass

    def get_tracks(self) -> GUITracksData:
        if self._store is not None and self._use_store_tracks:
            stored_tracks = self._store.get_all("tracks")
            if stored_tracks:
                return GUITracksData(
                    tracks=[GUIThreatTrack(**row) for row in stored_tracks if isinstance(row, dict)],
                    updatedAt=_now_iso(),
                )
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
        self._persist_rows("tracks", gui_tracks)
        result = GUITracksData(tracks=gui_tracks, updatedAt=_now_iso())
        emit_training_record("cop", {"query": "tracks"}, result)
        return result

    def get_threat_tracks(self) -> GUITracksData:
        """Threat-specific tracks from the threat dashboard provider."""
        if self._store is not None and self._use_store_threats:
            stored_threats = self._store.get_all("threats")
            if stored_threats:
                return GUITracksData(
                    tracks=[
                        GUIThreatTrack(**row)
                        for row in stored_threats
                        if isinstance(row, dict)
                    ],
                    updatedAt=_now_iso(),
                )
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
        self._persist_rows("threats", gui_tracks)
        result = GUITracksData(tracks=gui_tracks, updatedAt=_now_iso())
        emit_training_record("cop", {"query": "threat_tracks"}, result)
        return result

    def get_enriched_tracks(self) -> GUITracksData:
        """Pull from OperationalPictureService for full track enrichment."""
        try:
            from src.runtime.operational_picture_service import OperationalPictureService

            ops = OperationalPictureService()
            picture = ops.get_picture() if hasattr(ops, "get_picture") else {}
            picture_payload = self._normalize_picture_payload(picture)

            gui_tracks: List[GUIThreatTrack] = []
            track_index: Dict[str, GUIThreatTrack] = {}

            for entity in picture_payload.get("entities", []):
                if not isinstance(entity, dict):
                    continue
                track = self._build_track_from_picture_entity(entity)
                gui_tracks.append(track)
                track_index[track.id] = track

            # Tactical integration point: prefer confirmed fused tracks for reliable kinematics.
            for fused_track in self._get_confirmed_fused_tracks():
                fused_gui = self._build_track_from_fused_track(fused_track)
                existing = track_index.get(fused_gui.id)
                if existing is None:
                    gui_tracks.append(fused_gui)
                    track_index[fused_gui.id] = fused_gui
                else:
                    self._merge_track_enrichment(existing, fused_gui)

            if not gui_tracks:
                return self.get_tracks()
            updated_at = str(picture_payload.get("generated_at", _now_iso()))
            return GUITracksData(tracks=gui_tracks, updatedAt=updated_at)
        except Exception:
            return self.get_tracks()

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

    @staticmethod
    def _normalize_picture_payload(picture: Any) -> Dict[str, Any]:
        if isinstance(picture, dict):
            return picture
        if hasattr(picture, "to_dict"):
            try:
                payload = picture.to_dict()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                return {}
        if hasattr(picture, "model_dump"):
            try:
                payload = picture.model_dump()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                return {}
        return {}

    def _build_track_from_picture_entity(self, entity: Dict[str, Any]) -> GUIThreatTrack:
        track_id = str(entity.get("entity_id", entity.get("id", "UNKNOWN")))
        domain = self._infer_domain({"type": entity.get("entity_type", entity.get("type", ""))})
        confidence_raw = entity.get(
            "doctrine_adjusted_confidence",
            entity.get("raw_confidence", entity.get("confidence", 0.5)),
        )
        confidence = self._to_percent(confidence_raw)
        severity = self._threat_to_severity(entity.get("threat_level", "unknown"), confidence_raw)
        correlated = self._safe_str_list(entity.get("correlated_track_ids", entity.get("correlatedTrackIds", [])))
        summary = str(entity.get("classification") or entity.get("entity_type") or "Unknown track")
        last_seen = str(entity.get("last_updated", entity.get("timestamp", _now_iso())))

        pos_x, pos_y, pos_z = self._extract_xyz(entity.get("position"))
        latitude = longitude = altitude = None
        if pos_x is not None and pos_y is not None:
            latitude, longitude = self._grid_to_geo(pos_x, pos_y)
        if pos_z is not None:
            altitude = float(pos_z)

        speed, heading = self._velocity_to_kinematics(
            entity.get("velocity"),
            entity.get("speed_mps"),
            entity.get("heading_deg"),
        )
        identity_probs = self._build_identity_probabilities(
            entity.get("allegiance"),
            entity.get("identityProbabilities"),
        )
        source_attr = self._safe_str_list(entity.get("sourceAttribution", entity.get("sensor_sources", [])))
        history = self._history_to_geo(entity.get("history", []))
        action = self._recommended_action(domain, entity.get("threat_level", "unknown"), confidence)

        return GUIThreatTrack(
            id=track_id,
            domain=domain,
            confidence=confidence,
            severity=severity,
            correlatedTrackIds=correlated,
            summary=summary,
            lastSeen=last_seen,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            speed=speed,
            heading=heading,
            identityProbabilities=identity_probs,
            sourceAttribution=source_attr or None,
            trackHistory=history or None,
            recommendedAction=action,
        )

    def _build_track_from_fused_track(self, track: Any) -> GUIThreatTrack:
        track_data = track.to_dict() if hasattr(track, "to_dict") else (track if isinstance(track, dict) else {})
        track_id = str(track_data.get("track_id", track_data.get("id", "UNKNOWN")))
        classification = str(track_data.get("classification", "Fused tactical track") or "Fused tactical track")
        domain = self._infer_domain({"type": classification})
        confidence_raw = track_data.get("confidence", 0.5)
        confidence = self._to_percent(confidence_raw)
        severity = self._threat_to_severity(track_data.get("threat_level", "medium"), confidence_raw)
        last_seen = str(track_data.get("last_update", _now_iso()))

        pos_x, pos_y, pos_z = self._extract_xyz(track_data.get("position"))
        latitude = longitude = altitude = None
        if pos_x is not None and pos_y is not None:
            latitude, longitude = self._grid_to_geo(pos_x, pos_y)
        if pos_z is not None:
            altitude = float(pos_z)

        speed, heading = self._velocity_to_kinematics(track_data.get("velocity"), None, None)
        sources = self._safe_str_list(track_data.get("sensor_sources", []))
        history = self._history_to_geo(track_data.get("history", []))
        action = self._recommended_action(domain, track_data.get("threat_level", "medium"), confidence)

        return GUIThreatTrack(
            id=track_id,
            domain=domain,
            confidence=confidence,
            severity=severity,
            correlatedTrackIds=[],
            summary=classification,
            lastSeen=last_seen,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            speed=speed,
            heading=heading,
            sourceAttribution=sources or None,
            trackHistory=history or None,
            recommendedAction=action,
        )

    def _get_confirmed_fused_tracks(self) -> List[Any]:
        try:
            from src.api import threat_routes

            sensor_manager = getattr(threat_routes, "_sensor_manager", None)
            fuser = getattr(sensor_manager, "_fuser", None)
            if fuser is not None and hasattr(fuser, "get_confirmed_tracks"):
                tracks = fuser.get_confirmed_tracks()
                if isinstance(tracks, list):
                    return tracks
        except Exception:
            pass

        try:
            from src.sensor_fusion.track_fuser import TrackFuser

            fuser = TrackFuser()
            tracks = fuser.get_confirmed_tracks()
            return tracks if isinstance(tracks, list) else []
        except Exception:
            return []

    def _merge_track_enrichment(self, base: GUIThreatTrack, enriched: GUIThreatTrack) -> None:
        for key in ("latitude", "longitude", "altitude", "speed", "heading"):
            if getattr(base, key) is None and getattr(enriched, key) is not None:
                setattr(base, key, getattr(enriched, key))

        if enriched.sourceAttribution:
            merged_sources = set(base.sourceAttribution or [])
            merged_sources.update(enriched.sourceAttribution)
            base.sourceAttribution = sorted(merged_sources)

        if enriched.trackHistory:
            base.trackHistory = enriched.trackHistory

        if not base.recommendedAction and enriched.recommendedAction:
            base.recommendedAction = enriched.recommendedAction

        if enriched.correlatedTrackIds:
            merged_correlated = set(base.correlatedTrackIds or [])
            merged_correlated.update(enriched.correlatedTrackIds)
            base.correlatedTrackIds = sorted(merged_correlated)

        base.confidence = max(base.confidence, enriched.confidence)
        base.severity = max(base.severity, enriched.severity)

    @staticmethod
    def _extract_xyz(raw_position: Any) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        if not isinstance(raw_position, (list, tuple)):
            return None, None, None
        if len(raw_position) < 2:
            return None, None, None
        try:
            x = float(raw_position[0])
            y = float(raw_position[1])
            z = float(raw_position[2]) if len(raw_position) > 2 else None
            return x, y, z
        except Exception:
            return None, None, None

    @staticmethod
    def _grid_to_geo(x_meters: float, y_meters: float) -> Tuple[float, float]:
        # Tactical COP grids are mission-relative; convert to geodetic for map overlays.
        base_lat = 24.7136
        base_lon = 46.6753
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = meters_per_deg_lat * max(0.1, cos(radians(base_lat)))
        latitude = base_lat + (y_meters / meters_per_deg_lat)
        longitude = base_lon + (x_meters / meters_per_deg_lon)
        return round(latitude, 6), round(longitude, 6)

    @staticmethod
    def _velocity_to_kinematics(
        velocity: Any,
        speed_hint: Optional[Any],
        heading_hint: Optional[Any],
    ) -> Tuple[Optional[float], Optional[float]]:
        if isinstance(velocity, (list, tuple)) and len(velocity) >= 2:
            vx = float(velocity[0])
            vy = float(velocity[1])
            vz = float(velocity[2]) if len(velocity) > 2 else 0.0
            speed = round(sqrt(vx * vx + vy * vy + vz * vz), 2)
            heading = round((degrees(atan2(vy, vx)) + 360.0) % 360.0, 1)
            return speed, heading

        speed = round(float(speed_hint), 2) if speed_hint is not None else None
        heading = round(float(heading_hint), 1) if heading_hint is not None else None
        return speed, heading

    def _history_to_geo(self, raw_history: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_history, list):
            return []
        output: List[Dict[str, Any]] = []
        for point in raw_history:
            if not isinstance(point, dict):
                continue
            pos_x, pos_y, _ = self._extract_xyz(point.get("pos", point.get("position")))
            if pos_x is None or pos_y is None:
                continue
            latitude, longitude = self._grid_to_geo(pos_x, pos_y)
            output.append(
                {
                    "lat": latitude,
                    "lon": longitude,
                    "timestamp": str(point.get("ts", point.get("timestamp", _now_iso()))),
                }
            )
        return output

    @staticmethod
    def _safe_str_list(raw_values: Any) -> List[str]:
        if not isinstance(raw_values, list):
            return []
        return [str(v) for v in raw_values if str(v).strip()]

    def _threat_to_severity(self, threat_level: Any, confidence: Any) -> int:
        base_map = {
            "critical": 95,
            "high": 80,
            "medium": 55,
            "low": 30,
            "unknown": 40,
        }
        normalized = str(threat_level or "unknown").lower()
        base = base_map.get(normalized, 40)
        conf_pct = self._to_percent(confidence)
        return int(min(100, max(base, conf_pct)))

    @staticmethod
    def _build_identity_probabilities(
        allegiance: Any,
        provided: Any,
    ) -> Dict[str, float]:
        if isinstance(provided, dict):
            try:
                friendly = float(provided.get("friendly", 0.0))
                hostile = float(provided.get("hostile", 0.0))
                unknown = float(provided.get("unknown", 0.0))
            except Exception:
                friendly, hostile, unknown = 0.1, 0.1, 0.8
        else:
            friendly, hostile, unknown = 0.1, 0.1, 0.8
            normalized = str(allegiance or "unknown").lower()
            if normalized in {"friendly", "blue"}:
                friendly, hostile, unknown = 0.8, 0.05, 0.15
            elif normalized in {"hostile", "adversary", "red"}:
                friendly, hostile, unknown = 0.05, 0.85, 0.1
        total = max(1e-9, friendly + hostile + unknown)
        return {
            "friendly": round(max(0.0, friendly) / total, 3),
            "hostile": round(max(0.0, hostile) / total, 3),
            "unknown": round(max(0.0, unknown) / total, 3),
        }

    @staticmethod
    def _recommended_action(domain: str, threat_level: Any, severity: int) -> str:
        threat = str(threat_level or "unknown").lower()
        if domain == "cyber":
            return "Isolate affected network segment and maintain SIGINT monitoring posture."
        if threat in {"critical", "high"} or severity >= 80:
            return "Prioritize ISR cueing and maintain defensive intercept readiness."
        return "Continue track custody and collect corroborating sensor evidence."

    def _persist_rows(self, table: str, rows: list[GUIThreatTrack]) -> None:
        if self._store is None or not rows:
            return
        for row in rows:
            payload = row.model_dump() if hasattr(row, "model_dump") else row
            if isinstance(payload, dict):
                self._store.upsert(table, payload)
        if table == "tracks":
            self._use_store_tracks = True
        if table == "threats":
            self._use_store_threats = True
