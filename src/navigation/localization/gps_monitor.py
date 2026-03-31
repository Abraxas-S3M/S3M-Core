"""GPS integrity monitor for contested tactical navigation."""

from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Dict, List, Optional, Tuple

from src.navigation.models import GPSQuality, GPSStatus


class GPSMonitor:
    """Monitors GPS quality and denial/spoofing in contested EM battlespace."""

    def __init__(self, denial_threshold_hdop: float = 10.0, min_satellites: int = 4) -> None:
        if denial_threshold_hdop <= 0:
            raise ValueError("denial_threshold_hdop must be positive")
        if min_satellites < 1:
            raise ValueError("min_satellites must be at least 1")
        self.denial_threshold_hdop = float(denial_threshold_hdop)
        self.min_satellites = int(min_satellites)
        self.current_status = GPSStatus(
            quality=GPSQuality.UNKNOWN,
            satellites_visible=0,
            hdop=99.0,
            fix_type="none",
            last_fix_time=None,
            position=None,
        )
        self._quality_history: List[Dict[str, str]] = []
        self._last_position: Optional[Tuple[float, float, float]] = None
        self._last_good_time: Optional[datetime] = None
        self._forced_quality: Optional[GPSQuality] = None

    def update(
        self,
        satellites: int,
        hdop: float,
        fix_type: str,
        position: Optional[Tuple[float, float, float]] = None,
    ) -> GPSStatus:
        now = datetime.now(timezone.utc)
        if satellites < 0:
            raise ValueError("satellites must be non-negative")
        if hdop < 0:
            raise ValueError("hdop must be non-negative")
        fix_type_normalized = str(fix_type).strip().lower()

        inferred_quality = self._evaluate_quality(satellites=satellites, hdop=hdop, fix_type=fix_type_normalized)
        if self._is_spoofed(position):
            inferred_quality = GPSQuality.SPOOFED
        if self._forced_quality is not None:
            inferred_quality = self._forced_quality

        status = GPSStatus(
            quality=inferred_quality,
            satellites_visible=int(satellites),
            hdop=float(hdop),
            fix_type=fix_type_normalized,
            last_fix_time=now if fix_type_normalized != "none" else self.current_status.last_fix_time,
            position=position,
        )

        if inferred_quality in {GPSQuality.EXCELLENT, GPSQuality.GOOD}:
            self._last_good_time = now
        if position is not None:
            self._last_position = position

        if status.quality != self.current_status.quality:
            self._quality_history.append(
                {"timestamp": now.isoformat(), "from": self.current_status.quality.value, "to": status.quality.value}
            )
            if len(self._quality_history) > 1000:
                self._quality_history = self._quality_history[-1000:]
        self.current_status = status
        return status

    def _evaluate_quality(self, satellites: int, hdop: float, fix_type: str) -> GPSQuality:
        if satellites < self.min_satellites or fix_type == "none":
            return GPSQuality.DENIED
        if hdop < 2.0 and satellites > 8:
            return GPSQuality.EXCELLENT
        if hdop < 5.0 and satellites > 6:
            return GPSQuality.GOOD
        if hdop < self.denial_threshold_hdop and satellites >= self.min_satellites:
            return GPSQuality.DEGRADED
        return GPSQuality.DENIED

    def _is_spoofed(self, position: Optional[Tuple[float, float, float]]) -> bool:
        if position is None or self._last_position is None:
            return False
        dx = position[0] - self._last_position[0]
        dy = position[1] - self._last_position[1]
        dz = position[2] - self._last_position[2]
        return sqrt(dx * dx + dy * dy + dz * dz) > 1000.0

    def is_denied(self) -> bool:
        return self.current_status.quality in {GPSQuality.DENIED, GPSQuality.SPOOFED}

    def get_denial_duration(self) -> float:
        now = datetime.now(timezone.utc)
        if self._last_good_time is None:
            return 0.0
        if self.current_status.quality in {GPSQuality.EXCELLENT, GPSQuality.GOOD}:
            return 0.0
        return max((now - self._last_good_time).total_seconds(), 0.0)

    def get_quality_history(self, limit: int = 100) -> List[Dict[str, str]]:
        if limit <= 0:
            return []
        return self._quality_history[-limit:]

    def simulate_denial(self) -> None:
        self._forced_quality = GPSQuality.DENIED
        self.current_status.quality = GPSQuality.DENIED

    def simulate_restore(self) -> None:
        self._forced_quality = GPSQuality.GOOD
        self.current_status.quality = GPSQuality.GOOD
