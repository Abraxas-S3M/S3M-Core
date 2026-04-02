"""
S3M Force Tracker — Gap 2 of 7
Geo-temporal force status DB with predictive readiness logic.

The implementation is fully offline and in-memory for edge deployment.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("s3m.force_awareness")


class ForceStatus(str, Enum):
    FULLY_MISSION_CAPABLE = "FMC"
    PARTIALLY_MISSION_CAPABLE = "PMC"
    NON_MISSION_CAPABLE = "NMC"
    UNKNOWN = "UNK"

    @classmethod
    def from_value(cls, value: str | "ForceStatus") -> "ForceStatus":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            for item in cls:
                if normalized == item.value or normalized == item.name:
                    return item
        raise ValueError(f"Invalid force status: {value}")


class Domain(str, Enum):
    LAND = "LAND"
    AIR = "AIR"
    SEA = "SEA"
    CYBER = "CYBER"
    SPACE = "SPACE"

    @classmethod
    def from_value(cls, value: str | "Domain") -> "Domain":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            for item in cls:
                if normalized == item.value or normalized == item.name:
                    return item
        raise ValueError(f"Invalid domain: {value}")


def _validate_finite(name: str, value: float) -> float:
    if not isinstance(value, (float, int)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _parse_iso_timestamp(ts: str) -> datetime:
    if not isinstance(ts, str) or not ts.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    parsed = datetime.fromisoformat(ts)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class GeoPoint:
    lat: float
    lon: float
    alt_m: float = 0.0

    def __post_init__(self) -> None:
        self.lat = _validate_finite("lat", self.lat)
        self.lon = _validate_finite("lon", self.lon)
        self.alt_m = _validate_finite("alt_m", self.alt_m)
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError("lat must be between -90 and 90 degrees")
        if not -180.0 <= self.lon <= 180.0:
            raise ValueError("lon must be between -180 and 180 degrees")

    def haversine_km(self, other: "GeoPoint") -> float:
        if not isinstance(other, GeoPoint):
            raise ValueError("other must be a GeoPoint")
        earth_radius_km = 6371.0
        dlat = math.radians(other.lat - self.lat)
        dlon = math.radians(other.lon - self.lon)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(self.lat))
            * math.cos(math.radians(other.lat))
            * math.sin(dlon / 2) ** 2
        )
        return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class AssetState:
    asset_id: str
    callsign: str
    domain: Domain
    status: ForceStatus
    position: GeoPoint
    readiness_score: float  # 0.0 - 1.0
    fuel_pct: float = 1.0
    munitions_pct: float = 1.0
    maintenance_hours_due: float = 0.0
    crew_fatigue_score: float = 0.0  # 0=fresh, 1=exhausted
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("asset_id must be a non-empty string")
        if not isinstance(self.callsign, str) or not self.callsign.strip():
            raise ValueError("callsign must be a non-empty string")
        self.domain = Domain.from_value(self.domain)
        self.status = ForceStatus.from_value(self.status)
        if not isinstance(self.position, GeoPoint):
            raise ValueError("position must be a GeoPoint")

        self.readiness_score = _validate_finite("readiness_score", self.readiness_score)
        self.fuel_pct = _validate_finite("fuel_pct", self.fuel_pct)
        self.munitions_pct = _validate_finite("munitions_pct", self.munitions_pct)
        self.maintenance_hours_due = _validate_finite("maintenance_hours_due", self.maintenance_hours_due)
        self.crew_fatigue_score = _validate_finite("crew_fatigue_score", self.crew_fatigue_score)

        if not 0.0 <= self.readiness_score <= 1.0:
            raise ValueError("readiness_score must be between 0.0 and 1.0")
        if not 0.0 <= self.fuel_pct <= 1.0:
            raise ValueError("fuel_pct must be between 0.0 and 1.0")
        if not 0.0 <= self.munitions_pct <= 1.0:
            raise ValueError("munitions_pct must be between 0.0 and 1.0")
        if self.maintenance_hours_due < 0.0:
            raise ValueError("maintenance_hours_due must be >= 0.0")
        if not 0.0 <= self.crew_fatigue_score <= 1.0:
            raise ValueError("crew_fatigue_score must be between 0.0 and 1.0")

        # Military context: timestamps are normalized to UTC to keep joint-force
        # timeline alignment across platforms and tactical domains.
        self.timestamp = _parse_iso_timestamp(self.timestamp).isoformat()
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["domain"] = self.domain.value
        payload["status"] = self.status.value
        payload["position"] = asdict(self.position)
        return payload


class ForceStateStore:
    """Ring-buffer per asset; last N snapshots retained."""

    def __init__(self, history_depth: int = 1000) -> None:
        if not isinstance(history_depth, int) or history_depth <= 0:
            raise ValueError("history_depth must be a positive integer")
        self._store: Dict[str, List[AssetState]] = {}
        self._depth = history_depth

    def upsert(self, state: AssetState) -> None:
        if not isinstance(state, AssetState):
            raise ValueError("state must be an AssetState")
        if state.asset_id not in self._store:
            self._store[state.asset_id] = []
        buf = self._store[state.asset_id]
        buf.append(state)
        if len(buf) > self._depth:
            buf.pop(0)

    def latest(self, asset_id: str) -> Optional[AssetState]:
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("asset_id must be a non-empty string")
        buf = self._store.get(asset_id)
        return buf[-1] if buf else None

    def history(self, asset_id: str, n: int = 10) -> List[AssetState]:
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("asset_id must be a non-empty string")
        if not isinstance(n, int) or n <= 0:
            raise ValueError("n must be a positive integer")
        buf = self._store.get(asset_id, [])
        return buf[-n:]

    def all_latest(self) -> List[AssetState]:
        return [buf[-1] for buf in self._store.values() if buf]

    def assets_in_radius(self, center: GeoPoint, radius_km: float) -> List[AssetState]:
        if not isinstance(center, GeoPoint):
            raise ValueError("center must be a GeoPoint")
        radius_km = _validate_finite("radius_km", radius_km)
        if radius_km < 0.0:
            raise ValueError("radius_km must be >= 0.0")
        return [s for s in self.all_latest() if s.position.haversine_km(center) <= radius_km]


class PredictiveReadinessEngine:
    """
    Lightweight linear-regression predictor for readiness score.
    Predicts hours until asset falls below NMC threshold (score < 0.3).

    In production this can be swapped with a richer edge-deployable model.
    """

    NMC_THRESHOLD = 0.30
    MIN_HISTORY = 3

    def predict_nmc_hours(self, history: List[AssetState]) -> Optional[float]:
        if not isinstance(history, list) or any(not isinstance(s, AssetState) for s in history):
            raise ValueError("history must be a list of AssetState")
        if len(history) < self.MIN_HISTORY:
            return None

        try:
            t0 = _parse_iso_timestamp(history[0].timestamp).timestamp()
            points: List[Tuple[float, float]] = [
                (_parse_iso_timestamp(s.timestamp).timestamp() - t0, s.readiness_score)
                for s in history
            ]
        except ValueError:
            logger.warning("Invalid timestamp found in asset history; skipping readiness prediction.")
            return None

        n = len(points)
        sum_x = sum(p[0] for p in points)
        sum_y = sum(p[1] for p in points)
        sum_xy = sum(p[0] * p[1] for p in points)
        sum_x2 = sum(p[0] ** 2 for p in points)
        denom = n * sum_x2 - sum_x**2
        if abs(denom) < 1e-9:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n
        if slope >= 0:
            return None

        t_nmc_s = (self.NMC_THRESHOLD - intercept) / slope
        t_elapsed = points[-1][0]
        hours_remaining = max(0.0, (t_nmc_s - t_elapsed) / 3600.0)
        return round(hours_remaining, 1)


class ForceAwarenessManager:
    """
    Unified interface for command and API layers.

    Usage:
        fam = ForceAwarenessManager()
        fam.update(asset_state)
        snapshot = fam.get_full_picture()
    """

    def __init__(self, history_depth: int = 1000) -> None:
        self._store = ForceStateStore(history_depth=history_depth)
        self._predictor = PredictiveReadinessEngine()

    def update(self, state: AssetState) -> None:
        self._store.upsert(state)
        logger.debug("[FAM] Updated asset %s -> %s", state.asset_id, state.status.value)

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        s = self._store.latest(asset_id)
        if not s:
            return None
        hist = self._store.history(asset_id)
        hours_to_nmc = self._predictor.predict_nmc_hours(hist)
        return {
            **s.to_dict(),
            "predicted_nmc_hours": hours_to_nmc,
            # Military context: a 12-hour prediction horizon gives commanders a
            # practical lead time for maintenance and mission re-tasking.
            "alert": hours_to_nmc is not None and hours_to_nmc < 12,
        }

    def get_full_picture(self) -> Dict[str, Any]:
        assets: List[Dict[str, Any]] = []
        for s in self._store.all_latest():
            hist = self._store.history(s.asset_id)
            hours_to_nmc = self._predictor.predict_nmc_hours(hist)
            assets.append(
                {
                    **s.to_dict(),
                    "predicted_nmc_hours": hours_to_nmc,
                    "alert": hours_to_nmc is not None and hours_to_nmc < 12,
                }
            )

        by_status = {status.value: 0 for status in ForceStatus}
        for a in assets:
            by_status[a["status"]] = by_status.get(a["status"], 0) + 1

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_assets": len(assets),
            "by_status": by_status,
            "assets": assets,
        }

    def assets_near(self, lat: float, lon: float, radius_km: float) -> List[Dict[str, Any]]:
        center = GeoPoint(lat=lat, lon=lon)
        states = self._store.assets_in_radius(center=center, radius_km=radius_km)
        return [s.to_dict() for s in states]
