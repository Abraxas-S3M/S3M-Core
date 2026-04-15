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
from services.interop.symbology import SIDCGenerator, SymbologyMapper


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
        gui_tracks: List[GUIThreatTrack] = []
        if self._store is not None and self._use_store_tracks:
            stored_tracks = self._store.get_all("tracks")
            for row in stored_tracks:
                if isinstance(row, dict):
                    gui_tracks.append(GUIThreatTrack(**row))

        if not gui_tracks:
            raw_tracks = self._cop.get_tracks()
            for t in raw_tracks:
                domain = self._infer_domain(t)
                affiliation = self._infer_affiliation(t)
                gui_tracks.append(
                    GUIThreatTrack(
                        id=t.get("id", "UNKNOWN"),
                        domain=domain,
                        sidc=self._resolve_sidc(
                            affiliation=affiliation,
                            domain=domain,
                            entity_type=t.get("type"),
                        ),
                        confidence=self._to_percent(t.get("confidence", 0)),
                        severity=self._to_percent(t.get("threat_score", t.get("confidence", 0))),
                        correlatedTrackIds=list(t.get("correlated", [])),
                        summary=t.get("classification", t.get("type", "Unknown track")),
                        lastSeen=t.get("last_update", _now_iso()),
                    )
                )

        # Tactical COP requirement: include inbound coalition tracks from all interop gateways.
        interop_tracks = self._collect_inbound_coalition_tracks()
        if interop_tracks:
            gui_tracks = self._merge_gui_tracks(gui_tracks, interop_tracks)
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
            domain = str(t.get("category", "kinetic")).lower()
            affiliation = self._infer_affiliation(t)
            gui_tracks.append(GUIThreatTrack(
                id=t.get("id", "UNKNOWN"),
                domain=domain,
                sidc=self._resolve_sidc(
                    affiliation=affiliation,
                    domain=domain,
                    entity_type=t.get("type", t.get("title", t.get("description", ""))),
                ),
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

    def _collect_inbound_coalition_tracks(self) -> List[GUIThreatTrack]:
        inbound: List[GUIThreatTrack] = []
        for source, tracks in (
            ("cot", self._poll_cot_tracks()),
            ("nffi", self._poll_nffi_tracks()),
            ("jreap", self._poll_jreap_tracks()),
            ("oth_gold", self._poll_oth_tracks()),
        ):
            for track in tracks:
                gui_track = self._interop_track_to_gui_track(source=source, track=track)
                if gui_track is not None:
                    inbound.append(gui_track)
        return inbound

    @staticmethod
    def _poll_cot_tracks() -> List[Dict[str, Any]]:
        try:
            from src.api import cot_routes

            bridge = getattr(cot_routes, "_bridge", None)
            if bridge is None or not hasattr(bridge, "ingest_received"):
                return []
            rows = bridge.ingest_received()
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    @staticmethod
    def _poll_nffi_tracks() -> List[Dict[str, Any]]:
        try:
            from src.api import nffi_routes

            gateway = getattr(nffi_routes, "_nffi_gateway", None)
            if gateway is None or not hasattr(gateway, "receive_coalition_tracks"):
                return []
            rows = gateway.receive_coalition_tracks()
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    @staticmethod
    def _poll_jreap_tracks() -> List[Dict[str, Any]]:
        try:
            from src.api import jreap_routes

            bridge = getattr(jreap_routes, "_jreap_bridge", None)
            if bridge is None:
                return []
            if hasattr(bridge, "process_received"):
                bridge.process_received()
            if not hasattr(bridge, "get_tracks"):
                return []
            rows = bridge.get_tracks()
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    @staticmethod
    def _poll_oth_tracks() -> List[Dict[str, Any]]:
        try:
            from src.api import oth_routes

            adapter = getattr(oth_routes, "_oth_adapter", None)
            if adapter is None or not hasattr(adapter, "receive"):
                return []
            rows = adapter.receive()
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def _interop_track_to_gui_track(self, source: str, track: Dict[str, Any]) -> Optional[GUIThreatTrack]:
        if not isinstance(track, dict):
            return None

        track_id = str(
            track.get("id")
            or track.get("unit_id")
            or track.get("track_id")
            or track.get("uid")
            or f"{source}-unknown"
        ).strip()
        if not track_id:
            return None

        lat, lon, alt = self._extract_interop_position(track)
        domain = self._interop_domain(source=source, track=track)
        affiliation = self._infer_affiliation(track)
        summary = str(track.get("summary") or track.get("role") or track.get("entity_type") or f"{source} track")
        speed, heading = self._extract_interop_kinematics(track)
        sidc = self._resolve_sidc(
            affiliation=affiliation,
            domain=domain,
            entity_type=summary,
        )
        return GUIThreatTrack(
            id=track_id,
            domain=domain,
            sidc=sidc,
            confidence=self._to_percent(track.get("confidence", 0.8)),
            severity=self._to_percent(track.get("severity", track.get("confidence", 0.7))),
            correlatedTrackIds=self._safe_str_list(track.get("correlatedTrackIds", [])),
            summary=summary,
            lastSeen=str(track.get("lastSeen", track.get("updated_at", track.get("timestamp", _now_iso())))),
            latitude=lat,
            longitude=lon,
            altitude=alt,
            speed=speed,
            heading=heading,
            sourceAttribution=[source],
        )

    @classmethod
    def _extract_interop_position(cls, track: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        if isinstance(track.get("position"), (list, tuple)) and len(track.get("position")) >= 2:
            pos = track["position"]
            try:
                return (
                    float(pos[0]),
                    float(pos[1]),
                    float(pos[2]) if len(pos) > 2 else 0.0,
                )
            except Exception:
                return (None, None, None)

        pos_obj = track.get("position")
        if isinstance(pos_obj, dict):
            try:
                return (
                    float(pos_obj.get("lat", pos_obj.get("latitude"))),
                    float(pos_obj.get("lon", pos_obj.get("longitude"))),
                    float(pos_obj.get("alt", pos_obj.get("altitude", 0.0))),
                )
            except Exception:
                return (None, None, None)

        lat = track.get("lat", track.get("latitude"))
        lon = track.get("lon", track.get("longitude"))
        alt = track.get("hae", track.get("altitude", track.get("alt", 0.0)))
        try:
            if lat is None or lon is None:
                return (None, None, None)
            return (float(lat), float(lon), float(alt))
        except Exception:
            return (None, None, None)

    @staticmethod
    def _interop_domain(source: str, track: Dict[str, Any]) -> str:
        raw_domain = str(track.get("domain", "")).strip().lower()
        if raw_domain in {"air", "surface", "subsurface", "space"}:
            return raw_domain
        if raw_domain in {"maritime", "sea"}:
            return "surface"
        if source == "oth_gold":
            return "surface"
        if source == "jreap":
            return str(track.get("domain", "air")).strip().lower() or "air"
        return "land"

    @staticmethod
    def _extract_interop_kinematics(track: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        speed = track.get("speed", track.get("speed_mps"))
        if speed is None and isinstance(track.get("kinematics"), dict):
            speed = track["kinematics"].get("speed_mps")
        heading = track.get("heading", track.get("course", track.get("course_deg")))
        if heading is None and isinstance(track.get("kinematics"), dict):
            heading = track["kinematics"].get("course_deg")
        try:
            speed_value = round(float(speed), 2) if speed is not None else None
        except Exception:
            speed_value = None
        try:
            heading_value = round(float(heading), 1) if heading is not None else None
        except Exception:
            heading_value = None
        return speed_value, heading_value

    @staticmethod
    def _merge_gui_tracks(base_tracks: List[GUIThreatTrack], inbound_tracks: List[GUIThreatTrack]) -> List[GUIThreatTrack]:
        merged: Dict[str, GUIThreatTrack] = {track.id: track for track in base_tracks}
        for inbound in inbound_tracks:
            existing = merged.get(inbound.id)
            if existing is None:
                merged[inbound.id] = inbound
                continue
            if inbound.latitude is not None:
                existing.latitude = inbound.latitude
            if inbound.longitude is not None:
                existing.longitude = inbound.longitude
            if inbound.altitude is not None:
                existing.altitude = inbound.altitude
            if inbound.speed is not None:
                existing.speed = inbound.speed
            if inbound.heading is not None:
                existing.heading = inbound.heading
            existing.lastSeen = inbound.lastSeen
            existing.summary = inbound.summary or existing.summary
            existing.confidence = max(existing.confidence, inbound.confidence)
            existing.severity = max(existing.severity, inbound.severity)
            if inbound.sourceAttribution:
                current_sources = set(existing.sourceAttribution or [])
                current_sources.update(inbound.sourceAttribution)
                existing.sourceAttribution = sorted(current_sources)
            if not existing.sidc and inbound.sidc:
                existing.sidc = inbound.sidc
        return list(merged.values())

    def get_enriched_tracks(self) -> GUITracksData:
        """Pull from OperationalPictureService for full track enrichment."""
        try:
            from src.runtime.operational_picture_service import OperationalPictureService
            from src.sensor_fusion.stone_soup_bridge import StoneSoupBridge

            ops = OperationalPictureService()
            picture = ops.get_picture() if hasattr(ops, "get_picture") else {}
            picture_payload = self._normalize_picture_payload(picture)
            stone_soup_bridge = StoneSoupBridge()

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

            for track in gui_tracks:
                base_probabilities = getattr(track, "identityProbabilities", None)
                association_confidence = float(track.confidence) / 100.0 if track.confidence is not None else 0.0
                stone_soup_bridge.set_track_context(
                    track.id,
                    identity_hypotheses=base_probabilities if isinstance(base_probabilities, dict) else None,
                    association_confidence=association_confidence,
                )
                track.identityProbabilities = stone_soup_bridge.get_identity_probabilities(track.id)

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
            domain = cls._infer_domain({"type": entity_type})
            tracks.append(
                GUIThreatTrack(
                    id=str(raw_entity.get("entity_id", "UNKNOWN")),
                    domain=domain,
                    sidc=cls._resolve_sidc(
                        affiliation="hostile",
                        domain=domain,
                        entity_type=entity_type,
                    ),
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
        affiliation = self._infer_affiliation(entity)

        return GUIThreatTrack(
            id=track_id,
            domain=domain,
            sidc=self._resolve_sidc(
                affiliation=affiliation,
                domain=domain,
                entity_type=entity.get("entity_type", entity.get("type")),
            ),
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
        affiliation = self._infer_affiliation(track_data)

        return GUIThreatTrack(
            id=track_id,
            domain=domain,
            sidc=self._resolve_sidc(
                affiliation=affiliation,
                domain=domain,
                entity_type=classification,
            ),
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

        if not base.sidc and enriched.sidc:
            base.sidc = enriched.sidc

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
    def _infer_affiliation(payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return "unknown"
        for key in ("affiliation", "allegiance", "identity", "side"):
            value = str(payload.get(key, "")).strip().lower()
            if value in {"friendly", "friend", "blue", "own", "ally", "allied"}:
                return "friendly"
            if value in {"hostile", "enemy", "adversary", "red"}:
                return "hostile"
        summary = str(payload.get("classification", payload.get("type", ""))).lower()
        if "friendly" in summary or "ally" in summary:
            return "friendly"
        if "hostile" in summary or "enemy" in summary:
            return "hostile"
        return "unknown"

    @classmethod
    def _resolve_sidc(cls, affiliation: Any, domain: Any, entity_type: Any) -> str:
        sidc = SymbologyMapper.map_track_symbology(
            {
                "affiliation": str(affiliation) if affiliation is not None else "unknown",
                "domain": str(domain) if domain is not None else "land",
                "entity_type": str(entity_type) if entity_type is not None else "UNKNOWN",
            }
        )
        if SIDCGenerator.is_valid_sidc(sidc):
            return sidc
        return SIDCGenerator.generate(
            affiliation=str(affiliation) if affiliation is not None else "unknown",
            domain=str(domain) if domain is not None else "land",
            entity_type=str(entity_type) if entity_type is not None else "UNKNOWN",
        )

    @classmethod
    def _domain_to_symbol_name(cls, affiliation: Any, domain: Any, entity_type: Any) -> str:
        affiliation_token = cls._infer_affiliation({"affiliation": affiliation})
        affiliation_name = {
            "friendly": "friendly",
            "hostile": "enemy",
            "unknown": "unknown",
        }.get(affiliation_token, "unknown")

        domain_value = str(domain or "").strip().lower()
        domain_to_entity_name = {
            "air": "aircraft",
            "kinetic": "armored vehicle",
            "land": "armored vehicle",
            "ground": "armored vehicle",
            "cyber": "cyber warfare",
            "intel": "reconnaissance unit",
            "maritime": "surface vessel",
            "sea": "surface vessel",
            "subsurface": "submarine",
            "space": "satellite",
            "electronic": "electronic warfare unit",
        }
        entity_name = domain_to_entity_name.get(domain_value, "")
        if not entity_name:
            inferred_domain = cls._infer_domain({"type": entity_type})
            entity_name = domain_to_entity_name.get(inferred_domain, "unit")
        return f"{affiliation_name} {entity_name}".strip()

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
