"""HORIZON Tower adapter with centralized COP TrackStore."""

from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable


EARTH_RADIUS_M = 6_371_000.0


try:  # Dependency from Prompt 1.
    from src.platforms.common import PlatformAdapter  # type: ignore
except Exception:  # pragma: no cover - local fallback for isolated execution.
    @runtime_checkable
    class PlatformAdapter(Protocol):
        """Fallback platform adapter protocol."""

        def step(self, dt_seconds: float) -> None:
            """Advance adapter state."""

        def get_status(self) -> dict[str, Any]:
            """Return status snapshot."""


def _validate_lat_lon(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("latitude must be in [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("longitude must be in [-180, 180]")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    a_lat_r = math.radians(a_lat)
    a_lon_r = math.radians(a_lon)
    b_lat_r = math.radians(b_lat)
    b_lon_r = math.radians(b_lon)
    d_lat = b_lat_r - a_lat_r
    d_lon = b_lon_r - a_lon_r
    h = math.sin(d_lat / 2.0) ** 2 + math.cos(a_lat_r) * math.cos(b_lat_r) * math.sin(d_lon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(max(0.0, min(1.0, h))))


def _project_point(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    if distance_m <= 0.0:
        return lat, lon
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    brg = math.radians(bearing_deg)
    angular = distance_m / EARTH_RADIUS_M

    lat2 = math.asin(math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    lon2_norm = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
    return math.degrees(lat2), lon2_norm


def _as_track_dict(track: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(track)
    if "lat" not in payload or "lon" not in payload:
        raise ValueError("track requires lat and lon")

    lat = float(payload["lat"])
    lon = float(payload["lon"])
    _validate_lat_lon(lat, lon)

    payload["lat"] = lat
    payload["lon"] = lon
    payload["alt_m"] = float(payload.get("alt_m", 0.0))
    payload["confidence"] = _clamp(float(payload.get("confidence", 0.5)), 0.0, 1.0)
    payload["classification"] = str(payload.get("classification", "unknown")).strip() or "unknown"
    payload["sensor_type"] = str(payload.get("sensor_type", "unknown")).strip() or "unknown"
    payload["vx_mps"] = float(payload.get("vx_mps", 0.0))
    payload["vy_mps"] = float(payload.get("vy_mps", 0.0))
    raw_metadata = payload.get("metadata", {})
    if raw_metadata is None:
        raw_metadata = {}
    if not isinstance(raw_metadata, Mapping):
        raise ValueError("metadata must be a mapping if provided")
    payload["metadata"] = dict(raw_metadata)
    return payload


@dataclass
class _TrackRecord:
    track_id: str
    lat: float
    lon: float
    alt_m: float
    classification: str
    confidence: float
    sensor_type: str
    vx_mps: float
    vy_mps: float
    last_update_ts: float
    first_seen_ts: float
    updates: int = 1
    stale: bool = False
    source_weights: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "lat": self.lat,
            "lon": self.lon,
            "alt_m": self.alt_m,
            "classification": self.classification,
            "confidence": self.confidence,
            "sensor_type": self.sensor_type,
            "vx_mps": self.vx_mps,
            "vy_mps": self.vy_mps,
            "last_update_ts": self.last_update_ts,
            "first_seen_ts": self.first_seen_ts,
            "updates": self.updates,
            "stale": self.stale,
            "source_weights": dict(self.source_weights),
            "metadata": dict(self.metadata),
        }


class TrackStore:
    """
    Centralized COP track store.

    Features:
    - ingest_track / ingest_batch
    - position-based association
    - weighted merge for kinematics/classification confidence
    - stale aging and eviction
    - pub/sub for downstream consumers
    """

    def __init__(
        self,
        *,
        association_radius_m: float = 450.0,
        stale_after_s: float = 180.0,
        evict_after_s: float = 900.0,
    ) -> None:
        if association_radius_m <= 0.0:
            raise ValueError("association_radius_m must be > 0")
        if stale_after_s <= 0.0:
            raise ValueError("stale_after_s must be > 0")
        if evict_after_s <= stale_after_s:
            raise ValueError("evict_after_s must be > stale_after_s")

        self.association_radius_m = association_radius_m
        self.stale_after_s = stale_after_s
        self.evict_after_s = evict_after_s
        self._tracks: dict[str, _TrackRecord] = {}
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        if not callable(callback):
            raise ValueError("callback must be callable")
        with self._lock:
            self._subscribers.append(callback)

    def _publish(self, event: dict[str, Any]) -> None:
        subscribers: list[Callable[[dict[str, Any]], None]]
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                # Subscriber failures are isolated to keep COP updates resilient.
                continue

    def _find_association(self, incoming: dict[str, Any]) -> _TrackRecord | None:
        best: _TrackRecord | None = None
        best_distance = float("inf")
        for track in self._tracks.values():
            d = _distance_m(incoming["lat"], incoming["lon"], track.lat, track.lon)
            if d <= self.association_radius_m and d < best_distance:
                best = track
                best_distance = d
        return best

    def ingest_track(self, track: Mapping[str, Any], *, source: str | None = None, now_ts: float | None = None) -> dict[str, Any]:
        payload = _as_track_dict(track)
        source_name = (source or payload["sensor_type"]).strip() or "unknown"
        ts = float(now_ts) if now_ts is not None else time.time()

        with self._lock:
            explicit_track_id = str(payload.get("track_id", "")).strip()
            associated = self._tracks.get(explicit_track_id) if explicit_track_id else None
            if associated is None:
                associated = self._find_association(payload)

            if associated is None:
                track_id = explicit_track_id or f"trk-{uuid.uuid4().hex[:12]}"
                created = _TrackRecord(
                    track_id=track_id,
                    lat=payload["lat"],
                    lon=payload["lon"],
                    alt_m=payload["alt_m"],
                    classification=payload["classification"],
                    confidence=payload["confidence"],
                    sensor_type=payload["sensor_type"],
                    vx_mps=payload["vx_mps"],
                    vy_mps=payload["vy_mps"],
                    last_update_ts=ts,
                    first_seen_ts=ts,
                    updates=1,
                    stale=False,
                    source_weights={source_name: payload["confidence"] or 0.01},
                    metadata=dict(payload["metadata"]),
                )
                self._tracks[track_id] = created
                event = {"type": "track_created", "track": created.to_dict()}
                result = created.to_dict()
            else:
                old_confidence = associated.confidence
                old_weight = max(0.01, associated.confidence) * max(1.0, float(associated.updates))
                new_weight = max(0.01, payload["confidence"])
                total = old_weight + new_weight

                associated.lat = (associated.lat * old_weight + payload["lat"] * new_weight) / total
                associated.lon = (associated.lon * old_weight + payload["lon"] * new_weight) / total
                associated.alt_m = (associated.alt_m * old_weight + payload["alt_m"] * new_weight) / total
                associated.vx_mps = (associated.vx_mps * old_weight + payload["vx_mps"] * new_weight) / total
                associated.vy_mps = (associated.vy_mps * old_weight + payload["vy_mps"] * new_weight) / total
                associated.confidence = _clamp((associated.confidence * old_weight + payload["confidence"] * new_weight) / total, 0.0, 1.0)
                if payload["confidence"] >= old_confidence:
                    associated.classification = payload["classification"]
                    associated.sensor_type = payload["sensor_type"]
                associated.updates += 1
                associated.last_update_ts = ts
                associated.stale = False
                associated.source_weights[source_name] = associated.source_weights.get(source_name, 0.0) + new_weight
                associated.metadata.update(payload["metadata"])
                event = {"type": "track_updated", "track": associated.to_dict()}
                result = associated.to_dict()

        self._publish(event)
        return result

    def ingest_batch(
        self,
        tracks: Iterable[Mapping[str, Any]],
        *,
        source: str | None = None,
        now_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for track in tracks:
            output.append(self.ingest_track(track, source=source, now_ts=now_ts))
        return output

    def age_stale_tracks(self, *, now_ts: float | None = None) -> None:
        ts = float(now_ts) if now_ts is not None else time.time()
        evicted: list[str] = []
        with self._lock:
            for track in self._tracks.values():
                age_s = ts - track.last_update_ts
                track.stale = age_s >= self.stale_after_s

            for track_id, track in list(self._tracks.items()):
                if ts - track.last_update_ts >= self.evict_after_s:
                    evicted.append(track_id)
                    del self._tracks[track_id]

        for track_id in evicted:
            self._publish({"type": "track_evicted", "track_id": track_id})

    def get_tracks(self, *, include_stale: bool = False, now_ts: float | None = None) -> list[dict[str, Any]]:
        self.age_stale_tracks(now_ts=now_ts)
        with self._lock:
            tracks = [track.to_dict() for track in self._tracks.values() if include_stale or not track.stale]
        tracks.sort(key=lambda item: item["last_update_ts"], reverse=True)
        return tracks


class HorizonAdapter(PlatformAdapter):  # type: ignore[misc]
    """
    HORIZON fixed surveillance node.

    Tactical behavior notes:
    - Node is immobile (FIXED_NODE) and acts as centralized COP track fusion.
    - Simulates radar and EO/IR detections for persistent overwatch.
    - Provides cueing hooks for downstream effectors.
    """

    NODE_TYPE = "FIXED_NODE"

    def __init__(
        self,
        platform_id: str,
        node_lat: float,
        node_lon: float,
        *,
        node_alt_m: float = 0.0,
        radar_range_m: float = 120_000.0,
        eoir_range_m: float = 28_000.0,
        track_store: TrackStore | None = None,
    ) -> None:
        if not platform_id or not platform_id.strip():
            raise ValueError("platform_id must be non-empty")
        _validate_lat_lon(node_lat, node_lon)
        if node_alt_m < 0.0:
            raise ValueError("node_alt_m must be >= 0")
        if radar_range_m <= 0.0:
            raise ValueError("radar_range_m must be > 0")
        if eoir_range_m <= 0.0:
            raise ValueError("eoir_range_m must be > 0")

        self.platform_id = platform_id.strip()
        self.node_lat = node_lat
        self.node_lon = node_lon
        self.node_alt_m = node_alt_m
        self.radar_range_m = radar_range_m
        self.eoir_range_m = eoir_range_m
        self.track_store = track_store or TrackStore()
        self._cue_subscribers: list[Callable[[dict[str, Any]], None]] = []
        self._last_update_monotonic = time.monotonic()
        self._sim_now_ts = time.time()

    def subscribe_cues(self, callback: Callable[[dict[str, Any]], None]) -> None:
        if not callable(callback):
            raise ValueError("callback must be callable")
        self._cue_subscribers.append(callback)

    def _publish_cue(self, cue: dict[str, Any]) -> None:
        for callback in list(self._cue_subscribers):
            try:
                callback(cue)
            except Exception:
                continue

    def _relative_to_geo(self, bearing_deg: float, range_m: float) -> tuple[float, float]:
        if not (0.0 <= bearing_deg < 360.0):
            raise ValueError("bearing_deg must be in [0, 360)")
        if range_m < 0.0:
            raise ValueError("range_m must be >= 0")
        return _project_point(self.node_lat, self.node_lon, bearing_deg, range_m)

    def simulate_radar_detection(
        self,
        *,
        bearing_deg: float,
        range_m: float,
        radial_velocity_mps: float = 0.0,
        classification: str = "unknown",
        confidence: float = 0.68,
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        if range_m > self.radar_range_m:
            raise ValueError("range_m exceeds radar_range_m")
        if not classification.strip():
            raise ValueError("classification must be non-empty")

        lat, lon = self._relative_to_geo(bearing_deg, range_m)
        # Radar-origin velocity projection gives coarse but useful cueing vector for operators.
        heading_r = math.radians(bearing_deg)
        vx = radial_velocity_mps * math.cos(heading_r)
        vy = radial_velocity_mps * math.sin(heading_r)
        payload = {
            "lat": lat,
            "lon": lon,
            "alt_m": 0.0,
            "classification": classification.strip(),
            "confidence": _clamp(confidence, 0.0, 1.0),
            "sensor_type": "radar",
            "vx_mps": vx,
            "vy_mps": vy,
            "metadata": {"bearing_deg": bearing_deg, "range_m": range_m, "radial_velocity_mps": radial_velocity_mps},
        }
        return self.track_store.ingest_track(payload, source="radar", now_ts=now_ts)

    def simulate_eoir_detection(
        self,
        *,
        azimuth_deg: float,
        range_m: float,
        classification: str = "unknown",
        confidence: float = 0.82,
        altitude_m: float = 0.0,
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        if range_m > self.eoir_range_m:
            raise ValueError("range_m exceeds eoir_range_m")
        if altitude_m < 0.0:
            raise ValueError("altitude_m must be >= 0")
        if not classification.strip():
            raise ValueError("classification must be non-empty")

        lat, lon = self._relative_to_geo(azimuth_deg, range_m)
        payload = {
            "lat": lat,
            "lon": lon,
            "alt_m": altitude_m,
            "classification": classification.strip(),
            "confidence": _clamp(confidence, 0.0, 1.0),
            "sensor_type": "eo_ir",
            "vx_mps": 0.0,
            "vy_mps": 0.0,
            "metadata": {"azimuth_deg": azimuth_deg, "range_m": range_m},
        }
        return self.track_store.ingest_track(payload, source="eo_ir", now_ts=now_ts)

    def cue_effector(
        self,
        *,
        effector_id: str,
        track_id: str,
        action: str = "monitor",
        priority: int = 5,
        ttl_s: float = 120.0,
    ) -> dict[str, Any]:
        if not effector_id or not effector_id.strip():
            raise ValueError("effector_id must be non-empty")
        if not track_id or not track_id.strip():
            raise ValueError("track_id must be non-empty")
        if not action or not action.strip():
            raise ValueError("action must be non-empty")
        if priority < 1 or priority > 10:
            raise ValueError("priority must be in [1, 10]")
        if ttl_s <= 0.0:
            raise ValueError("ttl_s must be > 0")

        tracks = {track["track_id"]: track for track in self.track_store.get_tracks(include_stale=True)}
        if track_id not in tracks:
            raise KeyError(f"unknown track_id: {track_id}")

        cue = {
            "cue_id": f"cue-{uuid.uuid4().hex[:12]}",
            "tower_id": self.platform_id,
            "effector_id": effector_id.strip(),
            "track_id": track_id.strip(),
            "action": action.strip(),
            "priority": priority,
            "ttl_s": ttl_s,
            "issued_ts": time.time(),
            "target": {
                "lat": tracks[track_id]["lat"],
                "lon": tracks[track_id]["lon"],
                "alt_m": tracks[track_id]["alt_m"],
                "classification": tracks[track_id]["classification"],
                "confidence": tracks[track_id]["confidence"],
            },
        }
        self._publish_cue(cue)
        return cue

    def step(self, dt_seconds: float) -> None:
        if dt_seconds <= 0.0:
            raise ValueError("dt_seconds must be > 0")
        if dt_seconds > 3_600.0:
            raise ValueError("dt_seconds too large; cap is 3600 seconds")
        self._sim_now_ts += dt_seconds
        self.track_store.age_stale_tracks(now_ts=self._sim_now_ts)
        self._last_update_monotonic = time.monotonic()

    def get_status(self) -> dict[str, Any]:
        active_tracks = self.track_store.get_tracks(include_stale=False)
        all_tracks = self.track_store.get_tracks(include_stale=True)
        return {
            "platform_id": self.platform_id,
            "platform_type": self.NODE_TYPE,
            "position": {"lat": self.node_lat, "lon": self.node_lon, "alt_m": self.node_alt_m},
            "mobility": "fixed",
            "radar_range_m": self.radar_range_m,
            "eoir_range_m": self.eoir_range_m,
            "cop_tracks_active": len(active_tracks),
            "cop_tracks_total": len(all_tracks),
            "last_update_monotonic_s": self._last_update_monotonic,
        }

    def set_position(self, lat: float, lon: float, alt_m: float = 0.0) -> None:
        """
        Fixed-node mobility guard.

        The HORIZON tower is a static installation; this method intentionally blocks relocation.
        """
        _ = (lat, lon, alt_m)
        raise RuntimeError("HorizonAdapter is FIXED_NODE and cannot move")

