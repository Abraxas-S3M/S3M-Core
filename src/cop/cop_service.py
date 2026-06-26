"""COP service for Saudi MOD dashboard state and live updates.

Tactical context:
    This service prepares one normalized, dashboard-ready operational picture so
    command interfaces can render map posture, alerts, decisions, and panel
    summaries without exposing raw vault artifacts to frontend clients.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

from src.cop.adapters.open_c4isr_adapter import OpenC4ISRAdapter
from src.cop.cop_models import (
    CopAlert,
    CopDecision,
    CopFeature,
    CopFeedItem,
    CopPanelState,
    CopState,
    CopTrack,
)
from src.cop.demo_tracks import DEMO_TRACKS, THEATER_BOUNDS, build_scenario
from src.cop.event_bus import CopEventBus, get_event_bus
from src.storage.object_storage import ObjectStorageConnector, ObjectStorageError

# All future-safe demonstration tracks. ``saudi_mod`` is the primary demo track.
SUPPORTED_TRACKS: tuple[str, ...] = DEMO_TRACKS

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
        adapter: Optional[OpenC4ISRAdapter] = None,
        event_bus: Optional[CopEventBus] = None,
    ) -> None:
        self._cache_ttl_seconds = max(1.0, float(cache_ttl_seconds))
        self._max_keys_per_prefix = max(1, int(max_keys_per_prefix))
        self._max_object_size_bytes = max(4096, int(max_object_size_bytes))
        self._io_timeout_seconds = max(0.2, float(io_timeout_seconds))
        self._state_cache: Dict[str, Tuple[float, CopState]] = {}
        self._cache_lock = asyncio.Lock()
        self._connector: Optional[ObjectStorageConnector] = None
        self._connector_checked = False
        # Adapter seam into open C4ISR/COP inputs (TAK / ODIN / C2SIM-style).
        self._adapter = adapter or OpenC4ISRAdapter()
        # AI-ready event bus -- bridge toward the future quad-engine orchestrator.
        self._event_bus = event_bus or get_event_bus()

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
        """Build a deterministic, repeatable batch of COP stream events.

        Tactical context:
            Track coordinates are nudged each tick along their heading using a
            bounded sine envelope keyed only to the sequence number, so every
            demonstration replays identically and every contact stays inside the
            Saudi/Gulf theater bounds. Each update is also published to the
            AI-ready event bus as the bridge to the future quad-engine layer.
        """
        normalized_track = self._normalize_track(track)
        base_state = await self.get_state(normalized_track)
        timestamp = _now_iso()

        moved_tracks = self._propagate_tracks(base_state.tactical_tracks, sequence, timestamp)
        state_dict = _model_dump(base_state)
        state_dict["tactical_tracks"] = moved_tracks
        state_dict["timestamp"] = timestamp

        events: List[Dict[str, Any]] = [{"type": "cop_update", "state": state_dict}]

        # Publish per-track updates onto the AI-ready event bus (no LLM calls).
        for row in moved_tracks:
            self._event_bus.emit(
                track=normalized_track,
                event_type="track_update",
                payload=row,
                route_hint=self._route_hint_for_domain(str(row.get("domain", ""))),
                confidence=float(row.get("confidence", 0.0) or 0.0),
                requires_human_review=str(row.get("affiliation", "")) != "friendly",
                event_id=f"evt-{normalized_track}-track-{row.get('track_id')}-{sequence}",
                created_at=timestamp,
            )

        if base_state.feed_messages:
            item = _model_dump(base_state.feed_messages[sequence % len(base_state.feed_messages)])
            events.append({"type": "intel_feed", "item": item})
        risk_panel = self._panel_by_id(base_state.panel_summaries, "risk")
        if risk_panel is not None:
            events.append({"type": "risk_card", "panel": _model_dump(risk_panel)})
        if base_state.alerts:
            alert = _model_dump(base_state.alerts[sequence % len(base_state.alerts)])
            events.append({"type": "alert", "alert": alert})
            self._event_bus.emit(
                track=normalized_track,
                event_type="alert",
                payload=alert,
                route_hint="reasoning",
                confidence=0.5,
                requires_human_review=True,
                event_id=f"evt-{normalized_track}-alert-{alert.get('alert_id')}-{sequence}",
                created_at=timestamp,
            )
        if base_state.decisions:
            decision = _model_dump(base_state.decisions[sequence % len(base_state.decisions)])
            events.append({"type": "decision", "decision": decision})
            self._event_bus.emit(
                track=normalized_track,
                event_type="decision_request",
                payload=decision,
                route_hint="planning",
                confidence=0.5,
                requires_human_review=True,
                event_id=f"evt-{normalized_track}-decision-{decision.get('decision_id')}-{sequence}",
                created_at=timestamp,
            )

        events.append({"type": "system_status", "backend_health": base_state.backend_health, "timestamp": timestamp})
        return events

    def websocket_delay_seconds(self, track: str, sequence: int) -> float:
        """Fixed, deterministic stream cadence for demo stability."""
        self._normalize_track(track)
        return 2.0

    def _propagate_tracks(
        self, tracks: List[CopTrack], sequence: int, timestamp: str
    ) -> List[Dict[str, Any]]:
        """Deterministically shift tracks along heading within theater bounds."""
        (min_lat, min_lon), (max_lat, max_lon) = THEATER_BOUNDS
        moved: List[Dict[str, Any]] = []
        for track in tracks:
            data = _model_dump(track)
            speed = float(data.get("speed_kts", 0.0) or 0.0)
            if speed <= 0.0:
                # Stationary assets (sensors, cyber nodes) only refresh timestamp.
                data["last_update"] = timestamp
                moved.append(data)
                continue

            heading_rad = math.radians(float(data.get("heading_deg", 0.0) or 0.0))
            phase = self._track_phase(str(data.get("track_id", "")))
            # Bounded oscillation: amplitude scales with speed but is capped so
            # contacts never leave the theater. progress in [-1, 1].
            amplitude_nm = min(speed * 0.05, 30.0)
            progress = math.sin(0.35 * sequence + phase)
            amplitude_deg = amplitude_nm / 60.0

            base_lat = float(data.get("latitude", 0.0))
            base_lon = float(data.get("longitude", 0.0))
            cos_lat = max(0.2, math.cos(math.radians(base_lat)))
            new_lat = base_lat + amplitude_deg * math.cos(heading_rad) * progress
            new_lon = base_lon + (amplitude_deg / cos_lat) * math.sin(heading_rad) * progress

            data["latitude"] = round(self._clamp(new_lat, min_lat + 0.1, max_lat - 0.1), 5)
            data["longitude"] = round(self._clamp(new_lon, min_lon + 0.1, max_lon - 0.1), 5)
            data["last_update"] = timestamp
            moved.append(data)
        return moved

    @property
    def event_bus(self) -> CopEventBus:
        return self._event_bus

    @property
    def adapter(self) -> OpenC4ISRAdapter:
        return self._adapter

    def validate_track(self, track: str) -> str:
        return self._normalize_track(track)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _track_phase(track_id: str) -> float:
        """Deterministic per-track phase offset (process-independent)."""
        seed = sum(ord(char) for char in track_id)
        return (seed % 628) / 100.0

    @staticmethod
    def _route_hint_for_domain(domain: str) -> str:
        if domain == "cyber":
            return "reasoning"
        if domain in {"missile", "air", "maritime", "ground"}:
            return "tactical"
        return "tactical"

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
        """Assemble the deterministic demo COP payload for ``track``.

        Tactical context:
            Theater, map, features, decisions, and panel summaries come from the
            deterministic scenario seed. Tracks, alerts, and the feed are pulled
            through the Open C4ISR adapter seam so the data path mirrors a real
            TAK/ODIN ingest even though the first version is deterministic demo
            data. All timestamps are stamped at request time.
        """
        scenario = build_scenario(track)
        payload = scenario.to_payload()

        # Route tracks/alerts/feed through the adapter seam (deterministic today,
        # live TAK/ODIN tomorrow) and normalize tracks into the COP schema.
        adapter_tracks = self._adapter_tracks(track, fallback=payload["tactical_tracks"])
        adapter_alerts = self._adapter_rows(self._adapter.fetch_alerts, track, fallback=payload["alerts"])
        adapter_feed = self._adapter_rows(self._adapter.fetch_feed, track, fallback=payload["feed_messages"])

        payload["tactical_tracks"] = self._stamp_rows(adapter_tracks, "last_update", timestamp)
        payload["alerts"] = self._stamp_rows(adapter_alerts, "timestamp", timestamp)
        payload["decisions"] = self._stamp_rows(payload["decisions"], "timestamp", timestamp)
        payload["feed_messages"] = self._stamp_rows(adapter_feed, "timestamp", timestamp)

        payload["backend_health"] = {
            "status": "operational",
            "service": "cop_service",
            "cache_ttl_seconds": self._cache_ttl_seconds,
            "object_storage_configured": self._get_connector() is not None,
            "supported_tracks": list(SUPPORTED_TRACKS),
            "primary_demo_track": "saudi_mod",
            "adapter": self._adapter.health(),
            "ai_event_bus": {
                "enabled": True,
                "live_llm": False,
                "buffered_events": len(self._event_bus.recent(track, limit=200)),
            },
        }
        payload["timestamp"] = timestamp
        payload["data_source"] = "fallback"
        return payload

    def _adapter_tracks(self, track: str, *, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            raw_rows = self._adapter.fetch_tracks(track)
        except Exception:
            raw_rows = []
        if not raw_rows:
            return [dict(row) for row in fallback]
        normalized: List[Dict[str, Any]] = []
        for raw in raw_rows:
            try:
                normalized.append(_model_dump(self._adapter.normalize_track(raw)))
            except Exception:
                continue
        return normalized or [dict(row) for row in fallback]

    @staticmethod
    def _adapter_rows(fetcher: Any, track: str, *, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            rows = fetcher(track)
        except Exception:
            rows = []
        if not rows:
            return [dict(row) for row in fallback]
        return [dict(row) for row in rows if isinstance(row, dict)]

    @staticmethod
    def _stamp_rows(rows: List[Dict[str, Any]], field: str, timestamp: str) -> List[Dict[str, Any]]:
        stamped: List[Dict[str, Any]] = []
        for row in rows:
            updated = dict(row)
            if not updated.get(field):
                updated[field] = timestamp
            stamped.append(updated)
        return stamped

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
