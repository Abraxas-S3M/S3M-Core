"""COP service for Saudi MOD dashboard state and live updates.

Tactical context:
    This service prepares one normalized, dashboard-ready operational picture so
    command interfaces can render map posture, alerts, decisions, and panel
    summaries without exposing raw vault artifacts to frontend clients.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

from src.cop.cop_models import (
    CopAlert,
    CopDecision,
    CopFeature,
    CopFeedItem,
    CopMapConfig,
    CopPanelState,
    CopState,
    CopTheater,
    CopTrack,
)
from src.storage.object_storage import ObjectStorageConnector, ObjectStorageError

SUPPORTED_TRACKS: tuple[str, ...] = ("saudi_mod",)

INTEL_PREFIXES: tuple[str, ...] = (
    "intel/cop/",
    "intel/risk/",
    "intel/isr/",
    "intel/cyber/",
    "intel/maritime/",
    "intel/air_defense/",
    "intel/readiness/",
    "intel/logistics/",
    "intel/alerts/",
    "intel/decision_support/",
    "intel/bilingual_arabic/",
)

_JSON_SUFFIXES: tuple[str, ...] = (".json", ".JSON")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()  # type: ignore[attr-defined]


class CopService:
    """Build normalized COP payloads with bounded object-storage reads."""

    def __init__(
        self,
        *,
        cache_ttl_seconds: float = 20.0,
        max_keys_per_prefix: int = 4,
        max_object_size_bytes: int = 262_144,
        io_timeout_seconds: float = 1.5,
    ) -> None:
        self._cache_ttl_seconds = max(1.0, float(cache_ttl_seconds))
        self._max_keys_per_prefix = max(1, int(max_keys_per_prefix))
        self._max_object_size_bytes = max(4096, int(max_object_size_bytes))
        self._io_timeout_seconds = max(0.2, float(io_timeout_seconds))
        self._state_cache: Dict[str, Tuple[float, CopState]] = {}
        self._cache_lock = asyncio.Lock()
        self._connector: Optional[ObjectStorageConnector] = None
        self._connector_checked = False

    async def get_state(self, track: str, *, force_refresh: bool = False) -> CopState:
        normalized_track = self._normalize_track(track)
        if not force_refresh:
            cached = self._state_cache.get(normalized_track)
            if cached and (monotonic() - cached[0]) <= self._cache_ttl_seconds:
                return cached[1]

        async with self._cache_lock:
            if not force_refresh:
                cached = self._state_cache.get(normalized_track)
                if cached and (monotonic() - cached[0]) <= self._cache_ttl_seconds:
                    return cached[1]

            state = await asyncio.to_thread(self._build_state_sync, normalized_track)
            self._state_cache[normalized_track] = (monotonic(), state)
            return state

    async def get_map(self, track: str) -> Dict[str, Any]:
        state = await self.get_state(track)
        return {
            "track": state.track,
            "theater": _model_dump(state.theater),
            "map_config": _model_dump(state.map_config),
            "geospatial_features": [_model_dump(feature) for feature in state.geospatial_features],
            "timestamp": state.timestamp,
        }

    async def get_tracks(self, track: str) -> Dict[str, Any]:
        state = await self.get_state(track)
        return {
            "track": state.track,
            "tracks": [_model_dump(row) for row in state.tactical_tracks],
            "timestamp": state.timestamp,
        }

    async def get_alerts(self, track: str) -> Dict[str, Any]:
        state = await self.get_state(track)
        return {
            "track": state.track,
            "alerts": [_model_dump(row) for row in state.alerts],
            "timestamp": state.timestamp,
        }

    async def get_decisions(self, track: str) -> Dict[str, Any]:
        state = await self.get_state(track)
        return {
            "track": state.track,
            "decisions": [_model_dump(row) for row in state.decisions],
            "timestamp": state.timestamp,
        }

    async def get_feed(self, track: str) -> Dict[str, Any]:
        state = await self.get_state(track)
        return {
            "track": state.track,
            "feed": [_model_dump(row) for row in state.feed_messages],
            "timestamp": state.timestamp,
        }

    async def build_websocket_events(self, track: str, sequence: int) -> List[Dict[str, Any]]:
        state = await self.get_state(track, force_refresh=True)
        events: List[Dict[str, Any]] = [{"type": "cop_update", "state": _model_dump(state)}]

        if state.feed_messages:
            events.append({"type": "intel_feed", "item": _model_dump(state.feed_messages[sequence % len(state.feed_messages)])})
        risk_panel = self._panel_by_id(state.panel_summaries, "risk")
        if risk_panel is not None:
            events.append({"type": "risk_card", "panel": _model_dump(risk_panel)})
        if state.alerts:
            events.append({"type": "alert", "alert": _model_dump(state.alerts[sequence % len(state.alerts)])})
        if state.decisions:
            events.append({"type": "decision", "decision": _model_dump(state.decisions[sequence % len(state.decisions)])})

        events.append({"type": "system_status", "backend_health": state.backend_health, "timestamp": state.timestamp})
        return events

    def websocket_delay_seconds(self, track: str, sequence: int) -> float:
        normalized_track = self._normalize_track(track)
        seeded = random.Random(f"{normalized_track}:{sequence}")
        return round(seeded.uniform(3.0, 8.0), 2)

    def validate_track(self, track: str) -> str:
        return self._normalize_track(track)

    def _build_state_sync(self, track: str) -> CopState:
        timestamp = _now_iso()
        state_payload = self._build_fallback_payload(track=track, timestamp=timestamp)
        data_source = "fallback"

        remote_bundle = self._load_remote_bundle()
        if remote_bundle:
            self._merge_remote_payloads(state_payload, remote_bundle)
            data_source = "object_storage+fallback"

        state_payload["data_source"] = data_source
        state_payload["timestamp"] = timestamp
        return CopState(**state_payload)

    def _load_remote_bundle(self) -> Dict[str, List[Dict[str, Any]]]:
        connector = self._get_connector()
        if connector is None:
            return {}

        bundle: Dict[str, List[Dict[str, Any]]] = {}
        for prefix in INTEL_PREFIXES:
            try:
                payloads = self._load_prefix_payloads(connector=connector, prefix=prefix)
            except Exception:
                payloads = []
            if payloads:
                bundle[prefix] = payloads
        return bundle

    def _load_prefix_payloads(self, *, connector: ObjectStorageConnector, prefix: str) -> List[Dict[str, Any]]:
        keys = self._list_small_json_keys(connector=connector, prefix=prefix)
        payloads: List[Dict[str, Any]] = []
        for key in keys:
            try:
                payload = asyncio.run(self._read_json_with_timeout(connector=connector, key=key))
            except RuntimeError:
                # Tactical API calls may execute inside active event loops during tests.
                payload = self._read_json_safely(connector=connector, key=key)
            except Exception:
                payload = None
            sanitized = self._sanitize_payload(payload)
            if sanitized:
                payloads.append(sanitized)
        return payloads

    async def _read_json_with_timeout(
        self, *, connector: ObjectStorageConnector, key: str
    ) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._read_json_safely, connector=connector, key=key),
                timeout=self._io_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return None

    def _read_json_safely(self, *, connector: ObjectStorageConnector, key: str) -> Optional[Dict[str, Any]]:
        try:
            payload = connector.get_json(key)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _list_small_json_keys(self, *, connector: ObjectStorageConnector, prefix: str) -> List[str]:
        candidate_keys = self._list_bounded_keys(connector=connector, prefix=prefix)
        filtered: List[str] = []
        for key in candidate_keys:
            if not key.endswith(_JSON_SUFFIXES):
                continue
            try:
                size_bytes = connector.get_file_size(key)
            except Exception:
                continue
            if size_bytes <= self._max_object_size_bytes:
                filtered.append(key)
        return filtered[: self._max_keys_per_prefix]

    def _list_bounded_keys(self, *, connector: ObjectStorageConnector, prefix: str) -> List[str]:
        normalized_prefix = prefix.strip().lstrip("/")
        if not normalized_prefix.endswith("/"):
            normalized_prefix = f"{normalized_prefix}/"

        try:
            client = getattr(connector, "_client", None)
            if client is not None:
                response = client.list_objects_v2(
                    Bucket=connector.bucket_name,
                    Prefix=normalized_prefix,
                    MaxKeys=self._max_keys_per_prefix,
                )
                keys = [str(row.get("Key")) for row in response.get("Contents", []) if row.get("Key")]
                return sorted(keys)
        except Exception:
            pass

        try:
            return sorted(connector.list_keys(normalized_prefix))[: self._max_keys_per_prefix]
        except Exception:
            return []

    def _get_connector(self) -> Optional[ObjectStorageConnector]:
        if self._connector_checked:
            return self._connector
        self._connector_checked = True
        try:
            self._connector = ObjectStorageConnector.from_env()
        except (ObjectStorageError, ValueError):
            self._connector = None
        return self._connector

    def _sanitize_payload(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        blocked_tokens = ("secret", "password", "credential", "token", "access_key", "private_key")
        sanitized: Dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(token in lowered for token in blocked_tokens):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key_text] = value
            elif isinstance(value, dict):
                sanitized[key_text] = self._sanitize_payload(value)
            elif isinstance(value, list):
                sanitized_items: List[Any] = []
                for item in value:
                    if isinstance(item, dict):
                        sanitized_items.append(self._sanitize_payload(item))
                    elif isinstance(item, list):
                        sanitized_items.append(
                            [nested for nested in item if isinstance(nested, (str, int, float, bool, type(None)))]
                        )
                    elif isinstance(item, (str, int, float, bool)) or item is None:
                        sanitized_items.append(item)
                sanitized[key_text] = sanitized_items
        return sanitized

    def _build_fallback_payload(self, *, track: str, timestamp: str) -> Dict[str, Any]:
        theater = CopTheater(
            track=track,
            name="Saudi MOD Joint Operations Theater",
            center=[24.7136, 46.6753],
            bounds=[[15.5, 34.0], [32.8, 56.8]],
            focus_areas=[
                {"name": "Riyadh", "center": [24.7136, 46.6753], "type": "c2_hub"},
                {"name": "Jubail", "center": [27.0174, 49.6225], "type": "industrial_port"},
                {"name": "Arabian Gulf", "center": [26.1, 51.8], "type": "maritime_corridor"},
                {"name": "Red Sea", "center": [22.5, 38.8], "type": "strategic_sea_lane"},
                {"name": "Hormuz", "center": [26.57, 56.25], "type": "chokepoint"},
                {"name": "Bab al-Mandab", "center": [12.64, 43.34], "type": "chokepoint"},
                {"name": "Abu Musa", "center": [25.88, 55.03], "type": "island_outpost"},
                {"name": "Al Dhafra", "center": [24.25, 54.55], "type": "air_base"},
                {"name": "NAVCENT Bahrain", "center": [26.2285, 50.586], "type": "coalition_hq"},
            ],
        )
        map_config = CopMapConfig(
            center=[24.7136, 46.6753],
            bounds=[[15.5, 34.0], [32.8, 56.8]],
            layers=[
                "borders",
                "air_corridors",
                "maritime_routes",
                "critical_infrastructure",
                "threat_heatmap",
                "c2_nodes",
            ],
        )
        features = [
            CopFeature(
                feature_id="focus-riyadh",
                feature_type="focus_area",
                name="Riyadh Command Radius",
                geometry_type="Point",
                coordinates=[46.6753, 24.7136],
                properties={"priority": "critical", "domain": "command"},
            ),
            CopFeature(
                feature_id="focus-jubail",
                feature_type="focus_area",
                name="Jubail Energy Corridor",
                geometry_type="Point",
                coordinates=[49.6225, 27.0174],
                properties={"priority": "high", "domain": "logistics"},
            ),
            CopFeature(
                feature_id="route-hormuz-gulf",
                feature_type="sea_lane",
                name="Hormuz to Arabian Gulf Shipping Lane",
                geometry_type="LineString",
                coordinates=[[56.25, 26.57], [52.8, 26.1], [50.2, 26.2]],
                properties={"priority": "high", "domain": "maritime"},
            ),
            CopFeature(
                feature_id="route-red-sea",
                feature_type="sea_lane",
                name="Bab al-Mandab Transit Route",
                geometry_type="LineString",
                coordinates=[[43.34, 12.64], [41.8, 17.2], [39.1, 22.4]],
                properties={"priority": "high", "domain": "maritime"},
            ),
        ]
        tracks = [
            CopTrack(
                track_id="trk-saudi-air-001",
                callsign="RSAF-EAGLE-11",
                domain="air",
                affiliation="friendly",
                status="on_station",
                latitude=24.92,
                longitude=47.08,
                altitude_m=9700.0,
                speed_kts=420.0,
                heading_deg=102.0,
                confidence=0.96,
                last_update=timestamp,
                source="fallback_scenario",
            ),
            CopTrack(
                track_id="trk-gulf-surface-017",
                callsign="RSNF-FALCON-7",
                domain="maritime",
                affiliation="friendly",
                status="patrolling",
                latitude=26.18,
                longitude=51.34,
                altitude_m=0.0,
                speed_kts=21.0,
                heading_deg=148.0,
                confidence=0.91,
                last_update=timestamp,
                source="fallback_scenario",
            ),
            CopTrack(
                track_id="trk-unknown-air-404",
                callsign="UNKNOWN-404",
                domain="air",
                affiliation="unknown",
                status="monitor",
                latitude=25.84,
                longitude=54.74,
                altitude_m=10200.0,
                speed_kts=360.0,
                heading_deg=258.0,
                confidence=0.62,
                last_update=timestamp,
                source="fallback_scenario",
            ),
        ]
        alerts = [
            CopAlert(
                alert_id="alt-hormuz-001",
                category="maritime",
                severity="high",
                title="Elevated congestion near Hormuz",
                summary="Maritime density increased across the chokepoint; monitor convoy separation.",
                location="Strait of Hormuz",
                recommended_action="Increase ISR revisit rate and hold escort package at readiness level 2.",
                timestamp=timestamp,
            ),
            CopAlert(
                alert_id="alt-cyber-002",
                category="cyber",
                severity="medium",
                title="Anomalous scanning against C2 subnet",
                summary="Repeated reconnaissance signatures detected against command network segment.",
                location="Riyadh C2 enclave",
                recommended_action="Isolate exposed node and enforce packet capture for attribution.",
                timestamp=timestamp,
            ),
        ]
        decisions = [
            CopDecision(
                decision_id="dec-ops-101",
                title="Adjust maritime escort rotation",
                summary="Shift one escort vessel to eastern lane coverage during peak merchant traffic.",
                owner="MARITIME_DESK",
                status="recommended",
                priority="high",
                timestamp=timestamp,
            ),
            CopDecision(
                decision_id="dec-air-202",
                title="Prioritize air-defense sensor cueing",
                summary="Allocate additional radar dwell time over Abu Musa and gulf ingress vectors.",
                owner="AIR_DEFENSE_CELL",
                status="approved",
                priority="high",
                timestamp=timestamp,
            ),
        ]
        feed = [
            CopFeedItem(
                item_id="feed-001",
                channel="isr",
                title="ISR update",
                message="Persistent ISR confirms stable friendly posture around Riyadh and Jubail corridors.",
                language="en",
                tags=["isr", "cop", "saudi_mod"],
                timestamp=timestamp,
            ),
            CopFeedItem(
                item_id="feed-002",
                channel="command_chat",
                title="Command sync note",
                message="Joint desk requested consolidated risk and readiness snapshot for next briefing cycle.",
                language="en",
                tags=["command", "chat"],
                timestamp=timestamp,
            ),
        ]
        panels = [
            CopPanelState(
                panel_id="risk",
                title="Risk Panel",
                status="elevated",
                summary="Risk concentrated in maritime chokepoints and cyber reconnaissance activity.",
                metric={"overall_risk": 0.67, "trend_window_minutes": 30},
                trend="up",
                items=[{"zone": "Hormuz", "score": 0.79}, {"zone": "Riyadh C2", "score": 0.58}],
            ),
            CopPanelState(
                panel_id="cyber",
                title="Cyber Panel",
                status="guarded",
                summary="Network telemetry indicates low-volume probing with no confirmed breach.",
                metric={"alerts_last_hour": 5, "blocked_attempts": 19},
                trend="stable",
                items=[{"segment": "c2-core", "posture": "hardened"}],
            ),
            CopPanelState(
                panel_id="maritime",
                title="Maritime Panel",
                status="monitoring",
                summary="Escort lanes remain open with increased watch at Hormuz and Bab al-Mandab.",
                metric={"active_contacts": 24, "escort_assets_ready": 4},
                trend="up",
                items=[{"area": "Arabian Gulf", "traffic_level": "high"}],
            ),
            CopPanelState(
                panel_id="readiness",
                title="Readiness Panel",
                status="ready",
                summary="Air and naval readiness remain above baseline with reserve capacity available.",
                metric={"readiness_score": 0.9, "reserve_capacity": 0.24},
                trend="stable",
                items=[{"unit": "RSAF CAP", "status": "ready"}, {"unit": "RSNF Escort", "status": "ready"}],
            ),
            CopPanelState(
                panel_id="command_chat",
                title="Command / Chat Panel",
                status="active",
                summary="Command channel synchronized across mission desks with bilingual briefing queue.",
                metric={"active_threads": 6, "unread_messages": 2},
                trend="stable",
                items=[{"thread": "joint-ops", "priority": "high"}],
            ),
        ]
        backend_health = {
            "status": "operational",
            "service": "cop_service",
            "cache_ttl_seconds": self._cache_ttl_seconds,
            "object_storage_configured": self._get_connector() is not None,
            "supported_tracks": list(SUPPORTED_TRACKS),
        }

        return {
            "track": track,
            "theater": _model_dump(theater),
            "map_config": _model_dump(map_config),
            "geospatial_features": [_model_dump(row) for row in features],
            "tactical_tracks": [_model_dump(row) for row in tracks],
            "alerts": [_model_dump(row) for row in alerts],
            "decisions": [_model_dump(row) for row in decisions],
            "feed_messages": [_model_dump(row) for row in feed],
            "panel_summaries": [_model_dump(row) for row in panels],
            "backend_health": backend_health,
            "timestamp": timestamp,
            "data_source": "fallback",
        }

    def _merge_remote_payloads(self, state_payload: Dict[str, Any], remote_bundle: Dict[str, List[Dict[str, Any]]]) -> None:
        cop_items = remote_bundle.get("intel/cop/", [])
        for payload in cop_items:
            self._merge_cop_payload(state_payload, payload)

        self._merge_alert_like_payloads(state_payload, remote_bundle.get("intel/alerts/", []))
        self._merge_decisions_payloads(state_payload, remote_bundle.get("intel/decision_support/", []))
        self._merge_feed_payloads(state_payload, remote_bundle.get("intel/isr/", []))
        self._merge_feed_payloads(state_payload, remote_bundle.get("intel/bilingual_arabic/", []))
        self._merge_panel_payload(state_payload, "risk", remote_bundle.get("intel/risk/", []))
        self._merge_panel_payload(state_payload, "cyber", remote_bundle.get("intel/cyber/", []))
        self._merge_panel_payload(state_payload, "maritime", remote_bundle.get("intel/maritime/", []))
        self._merge_panel_payload(state_payload, "readiness", remote_bundle.get("intel/readiness/", []))
        self._merge_panel_payload(state_payload, "logistics", remote_bundle.get("intel/logistics/", []))
        self._merge_panel_payload(state_payload, "air_defense", remote_bundle.get("intel/air_defense/", []))

    def _merge_cop_payload(self, state_payload: Dict[str, Any], payload: Dict[str, Any]) -> None:
        if isinstance(payload.get("theater"), dict):
            merged_theater = dict(state_payload["theater"])
            merged_theater.update(payload["theater"])
            state_payload["theater"] = merged_theater
        if isinstance(payload.get("map_config"), dict):
            merged_map = dict(state_payload["map_config"])
            merged_map.update(payload["map_config"])
            state_payload["map_config"] = merged_map

        feature_rows = payload.get("geospatial_features", payload.get("features"))
        track_rows = payload.get("tactical_tracks", payload.get("tracks"))
        feed_rows = payload.get("feed_messages", payload.get("feed"))
        panel_rows = payload.get("panel_summaries", payload.get("panels"))
        alert_rows = payload.get("alerts")
        decision_rows = payload.get("decisions")

        merged_features = self._coerce_features(feature_rows)
        if merged_features:
            state_payload["geospatial_features"] = merged_features
        merged_tracks = self._coerce_tracks(track_rows)
        if merged_tracks:
            state_payload["tactical_tracks"] = merged_tracks
        merged_feed = self._coerce_feed(feed_rows)
        if merged_feed:
            state_payload["feed_messages"] = merged_feed
        merged_panels = self._coerce_panels(panel_rows)
        if merged_panels:
            state_payload["panel_summaries"] = merged_panels
        merged_alerts = self._coerce_alerts(alert_rows)
        if merged_alerts:
            state_payload["alerts"] = merged_alerts
        merged_decisions = self._coerce_decisions(decision_rows)
        if merged_decisions:
            state_payload["decisions"] = merged_decisions

    def _merge_alert_like_payloads(self, state_payload: Dict[str, Any], payloads: List[Dict[str, Any]]) -> None:
        collected: List[Dict[str, Any]] = []
        for payload in payloads:
            rows = payload.get("alerts", payload.get("items", payload.get("records")))
            collected.extend(self._coerce_alerts(rows))
        if collected:
            state_payload["alerts"] = collected

    def _merge_decisions_payloads(self, state_payload: Dict[str, Any], payloads: List[Dict[str, Any]]) -> None:
        collected: List[Dict[str, Any]] = []
        for payload in payloads:
            rows = payload.get("decisions", payload.get("items", payload.get("recommendations")))
            collected.extend(self._coerce_decisions(rows))
        if collected:
            state_payload["decisions"] = collected

    def _merge_feed_payloads(self, state_payload: Dict[str, Any], payloads: List[Dict[str, Any]]) -> None:
        collected: List[Dict[str, Any]] = []
        for payload in payloads:
            rows = payload.get("feed_messages", payload.get("feed", payload.get("items")))
            collected.extend(self._coerce_feed(rows))
        if collected:
            state_payload["feed_messages"] = collected

    def _merge_panel_payload(self, state_payload: Dict[str, Any], panel_id: str, payloads: List[Dict[str, Any]]) -> None:
        if not payloads:
            return
        panel_rows = state_payload.get("panel_summaries", [])
        normalized_rows = [row for row in panel_rows if isinstance(row, dict)]
        target = next((row for row in normalized_rows if str(row.get("panel_id", "")) == panel_id), None)
        base = dict(target) if target is not None else {"panel_id": panel_id, "title": panel_id.replace("_", " ").title()}
        for payload in payloads:
            if isinstance(payload.get("panel"), dict):
                base.update(payload["panel"])
            elif isinstance(payload.get(panel_id), dict):
                base.update(payload[panel_id])
            elif isinstance(payload.get("summary"), str):
                base["summary"] = payload["summary"]
                base["status"] = str(payload.get("status", base.get("status", "monitoring")))
        try:
            replacement = _model_dump(CopPanelState(**base))
        except Exception:
            return
        replaced = False
        normalized_panels: List[Dict[str, Any]] = []
        for row in normalized_rows:
            if str(row.get("panel_id")) == panel_id:
                normalized_panels.append(replacement)
                replaced = True
            else:
                normalized_panels.append(row)
        if not replaced:
            normalized_panels.append(replacement)
        state_payload["panel_summaries"] = normalized_panels

    def _coerce_features(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        items: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            payload = dict(row)
            payload.setdefault("feature_id", str(payload.get("id", f"feature-{idx+1}")))
            payload.setdefault("feature_type", str(payload.get("feature_type", payload.get("type", "overlay"))))
            payload.setdefault("name", str(payload.get("name", payload["feature_id"])))
            payload.setdefault("geometry_type", str(payload.get("geometry_type", payload.get("geometry", "Point"))))
            coordinates = payload.get("coordinates", [])
            if not isinstance(coordinates, list):
                coordinates = []
            payload["coordinates"] = coordinates
            payload["properties"] = payload.get("properties", {}) if isinstance(payload.get("properties"), dict) else {}
            try:
                items.append(_model_dump(CopFeature(**payload)))
            except Exception:
                continue
        return items

    def _coerce_tracks(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        items: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            payload = dict(row)
            payload.setdefault("track_id", str(payload.get("id", payload.get("unit_id", f"track-{idx+1}"))))
            payload.setdefault("callsign", str(payload.get("callsign", payload["track_id"])))
            payload.setdefault("domain", str(payload.get("domain", "unknown")))
            payload.setdefault("affiliation", str(payload.get("affiliation", "unknown")))
            payload.setdefault("status", str(payload.get("status", "monitor")))
            payload.setdefault("latitude", float(payload.get("latitude", payload.get("lat", 24.7136))))
            payload.setdefault("longitude", float(payload.get("longitude", payload.get("lon", 46.6753))))
            payload.setdefault("altitude_m", float(payload.get("altitude_m", payload.get("altitude", 0.0))))
            payload.setdefault("speed_kts", float(payload.get("speed_kts", payload.get("speed", 0.0))))
            payload.setdefault("heading_deg", float(payload.get("heading_deg", payload.get("heading", 0.0))))
            payload.setdefault("confidence", float(payload.get("confidence", 0.5)))
            payload.setdefault("last_update", str(payload.get("last_update", _now_iso())))
            payload.setdefault("source", str(payload.get("source", "object_storage")))
            try:
                items.append(_model_dump(CopTrack(**payload)))
            except Exception:
                continue
        return items

    def _coerce_alerts(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        items: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            payload = dict(row)
            payload.setdefault("alert_id", str(payload.get("id", f"alert-{idx+1}")))
            payload.setdefault("category", str(payload.get("category", "general")))
            payload.setdefault("severity", str(payload.get("severity", "medium")))
            payload.setdefault("title", str(payload.get("title", "Operational alert")))
            payload.setdefault("summary", str(payload.get("summary", payload.get("description", "No summary."))))
            payload.setdefault("status", str(payload.get("status", "active")))
            payload.setdefault(
                "recommended_action",
                str(payload.get("recommended_action", "Maintain surveillance and update command desk.")),
            )
            payload.setdefault("timestamp", str(payload.get("timestamp", _now_iso())))
            try:
                items.append(_model_dump(CopAlert(**payload)))
            except Exception:
                continue
        return items

    def _coerce_decisions(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        items: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            payload = dict(row)
            payload.setdefault("decision_id", str(payload.get("id", f"decision-{idx+1}")))
            payload.setdefault("title", str(payload.get("title", "Decision recommendation")))
            payload.setdefault("summary", str(payload.get("summary", payload.get("description", "No summary."))))
            payload.setdefault("owner", str(payload.get("owner", payload.get("cell", "OPS_CELL"))))
            payload.setdefault("status", str(payload.get("status", "recommended")))
            payload.setdefault("priority", str(payload.get("priority", "medium")))
            payload.setdefault("timestamp", str(payload.get("timestamp", _now_iso())))
            try:
                items.append(_model_dump(CopDecision(**payload)))
            except Exception:
                continue
        return items

    def _coerce_feed(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        items: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            payload = dict(row)
            payload.setdefault("item_id", str(payload.get("id", f"feed-{idx+1}")))
            payload.setdefault("channel", str(payload.get("channel", "intel")))
            payload.setdefault("title", str(payload.get("title", "Feed update")))
            payload.setdefault("message", str(payload.get("message", payload.get("summary", "No message."))))
            payload.setdefault("language", str(payload.get("language", "en")))
            tags = payload.get("tags", [])
            payload["tags"] = tags if isinstance(tags, list) else []
            payload.setdefault("timestamp", str(payload.get("timestamp", _now_iso())))
            try:
                items.append(_model_dump(CopFeedItem(**payload)))
            except Exception:
                continue
        return items

    def _coerce_panels(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        items: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            payload = dict(row)
            payload.setdefault("panel_id", str(payload.get("id", f"panel-{idx+1}")))
            payload.setdefault("title", str(payload.get("title", payload["panel_id"])))
            payload.setdefault("status", str(payload.get("status", "monitoring")))
            payload.setdefault("summary", str(payload.get("summary", "Panel summary unavailable.")))
            metric = payload.get("metric", {})
            payload["metric"] = metric if isinstance(metric, dict) else {}
            payload.setdefault("trend", str(payload.get("trend", "stable")))
            items_value = payload.get("items", [])
            payload["items"] = items_value if isinstance(items_value, list) else []
            try:
                items.append(_model_dump(CopPanelState(**payload)))
            except Exception:
                continue
        return items

    @staticmethod
    def _panel_by_id(rows: List[CopPanelState], panel_id: str) -> Optional[CopPanelState]:
        for row in rows:
            if str(getattr(row, "panel_id", "")) == panel_id:
                return row
        return None

    @staticmethod
    def _normalize_track(track: str) -> str:
        normalized_track = str(track).strip().lower()
        if normalized_track not in SUPPORTED_TRACKS:
            raise ValueError(f"Unsupported COP track: {normalized_track}")
        return normalized_track
