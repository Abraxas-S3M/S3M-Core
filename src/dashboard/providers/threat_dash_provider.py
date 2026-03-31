"""Threat dashboard provider for Layer 06 tactical intelligence panels."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.dashboard.providers.helpers import coerce_float, now_iso, normalize_position_dict
from src.dashboard.providers.runtime_store import get_runtime_state


LEVEL_WEIGHT = {
    "CRITICAL": 1.0,
    "HIGH": 0.85,
    "MEDIUM": 0.6,
    "LOW": 0.35,
    "INFO": 0.2,
}


class ThreatDashProvider:
    """Aggregate threat manager + sensor manager data with safe fallbacks."""

    def __init__(self) -> None:
        self._threat_manager = None
        self._sensor_manager = None
        self._available = {
            "threat_manager": False,
            "sensor_manager": False,
        }
        self._init_clients()

    def _init_clients(self) -> None:
        try:
            from src.threat_detection.threat_manager import ThreatManager

            self._threat_manager = ThreatManager()
            self._available["threat_manager"] = True
        except Exception:
            self._threat_manager = None
            self._available["threat_manager"] = False

        try:
            from src.sensor_fusion.sensor_manager import SensorManager

            self._sensor_manager = SensorManager()
            self._available["sensor_manager"] = True
        except Exception:
            self._sensor_manager = None
            self._available["sensor_manager"] = False

    def _normalize_event(self, event: Any) -> Dict[str, Any]:
        if hasattr(event, "to_dict"):
            try:
                raw = event.to_dict()
            except Exception:
                raw = {}
        elif isinstance(event, dict):
            raw = dict(event)
        else:
            raw = dict(getattr(event, "__dict__", {}))

        level = str(raw.get("level", "INFO")).upper()
        source = raw.get("source", "UNKNOWN")
        if isinstance(source, dict):
            source = source.get("value", "UNKNOWN")
        category = raw.get("category", "UNKNOWN")
        if isinstance(category, dict):
            category = category.get("value", "UNKNOWN")
        position = normalize_position_dict(raw.get("location", raw.get("position")))
        timestamp = raw.get("timestamp", now_iso())
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        return {
            "id": str(raw.get("event_id", raw.get("id", "unknown"))),
            "timestamp": str(timestamp),
            "level": level,
            "category": str(category),
            "source": str(source),
            "title": str(raw.get("title", "Threat event")),
            "description": str(raw.get("description", "")),
            "confidence": coerce_float(raw.get("confidence", 0.0), 0.0),
            "position": (position["x"], position["y"], position["z"]),
        }

    def get_threat_feed(self, level: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        level_filter = str(level).upper() if level else None
        events: List[Dict[str, Any]] = []

        if self._threat_manager is not None:
            try:
                raw_events = self._threat_manager.get_threats(level=level_filter, limit=safe_limit)
                events = [self._normalize_event(event) for event in raw_events]
            except Exception:
                events = []

        if not events:
            runtime_events = get_runtime_state().get("threats", [])
            if isinstance(runtime_events, list):
                for item in runtime_events:
                    if not isinstance(item, dict):
                        continue
                    normalized = self._normalize_event(item)
                    if level_filter and normalized["level"] != level_filter:
                        continue
                    events.append(normalized)
                    if len(events) >= safe_limit:
                        break

        return events[:safe_limit]

    def _timeline(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)
        bucket_counts: Dict[str, int] = defaultdict(int)

        for event in events:
            ts_val = event.get("timestamp")
            try:
                ts = datetime.fromisoformat(str(ts_val))
            except Exception:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < start:
                continue
            minute = (ts.minute // 5) * 5
            bucket = ts.replace(minute=minute, second=0, microsecond=0).isoformat()
            bucket_counts[bucket] += 1

        output: List[Dict[str, Any]] = []
        cursor = start.replace(minute=(start.minute // 5) * 5, second=0, microsecond=0)
        while cursor <= now:
            key = cursor.isoformat()
            output.append({"bucket": key, "count": bucket_counts.get(key, 0)})
            cursor += timedelta(minutes=5)
        return output

    def get_threat_stats(self) -> Dict[str, Any]:
        events = self.get_threat_feed(limit=500)
        by_level = Counter(event.get("level", "INFO") for event in events)
        by_category = Counter(event.get("category", "UNKNOWN") for event in events)
        by_source = Counter(event.get("source", "UNKNOWN") for event in events)

        return {
            "total_events": len(events),
            "critical": int(by_level.get("CRITICAL", 0)),
            "high": int(by_level.get("HIGH", 0)),
            "active_sensors": len([s for s in self.get_sensor_health() if s.get("status") == "active"]),
            "by_level": dict(by_level),
            "by_category": dict(by_category),
            "by_source": dict(by_source),
            "timeline": self._timeline(events),
        }

    def get_threat_heatmap(self) -> List[Dict[str, Any]]:
        events = self.get_threat_feed(limit=500)
        grid: Dict[Tuple[int, int], Dict[str, Any]] = {}
        spacing = 100.0

        for event in events:
            pos = event.get("position", (0.0, 0.0, 0.0))
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                continue
            x = coerce_float(pos[0], 0.0)
            y = coerce_float(pos[1], 0.0)
            gx = int(x // spacing)
            gy = int(y // spacing)
            cell = grid.setdefault((gx, gy), {"count": 0, "weight": 0.0, "categories": Counter()})
            cell["count"] += 1
            cell["weight"] += LEVEL_WEIGHT.get(str(event.get("level", "INFO")).upper(), 0.2)
            cell["categories"][str(event.get("category", "UNKNOWN"))] += 1

        heatmap: List[Dict[str, Any]] = []
        for (gx, gy), cell in grid.items():
            avg_weight = cell["weight"] / max(cell["count"], 1)
            dominant_category = "UNKNOWN"
            if cell["categories"]:
                dominant_category = cell["categories"].most_common(1)[0][0]
            heatmap.append(
                {
                    "position": ((gx * spacing) + (spacing / 2), (gy * spacing) + (spacing / 2)),
                    "intensity": round(cell["count"] * avg_weight, 3),
                    "category": dominant_category,
                }
            )

        heatmap.sort(key=lambda item: item["intensity"], reverse=True)
        return heatmap

    def get_sensor_health(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        sensor_health: List[Dict[str, Any]] = []

        if self._sensor_manager is not None:
            try:
                sensors = self._sensor_manager.get_sensors()
                for sensor in sensors:
                    if not isinstance(sensor, dict):
                        continue
                    registered_at = sensor.get("registered_at", now_iso())
                    try:
                        ts = datetime.fromisoformat(str(registered_at))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    except Exception:
                        ts = now
                    age = (now - ts).total_seconds()
                    status = "active" if age <= 600 else "stale"
                    sensor_health.append(
                        {
                            "sensor_id": str(sensor.get("sensor_id", "unknown")),
                            "type": str(sensor.get("sensor_type", "UNKNOWN")),
                            "last_reading_time": ts.isoformat(),
                            "readings_count": 0,
                            "status": status,
                        }
                    )
            except Exception:
                sensor_health = []

        if not sensor_health:
            runtime_sensors = get_runtime_state().get("sensors", [])
            if isinstance(runtime_sensors, list):
                for item in runtime_sensors:
                    if not isinstance(item, dict):
                        continue
                    sensor_health.append(
                        {
                            "sensor_id": str(item.get("sensor_id", "unknown")),
                            "type": str(item.get("type", "SIMULATED")),
                            "last_reading_time": str(item.get("last_reading_time", now_iso())),
                            "readings_count": int(item.get("readings_count", 0)),
                            "status": str(item.get("status", "offline")),
                        }
                    )

        return sensor_health

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational" if self._available["threat_manager"] else "degraded",
            "threat_manager": self._available["threat_manager"],
            "sensor_manager": self._available["sensor_manager"],
        }

