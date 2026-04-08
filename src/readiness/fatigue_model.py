"""Dawson-Reid fatigue model for military shift-readiness scoring."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Tuple


class DawsonReidFatigueModel:
    """Compute fatigue-adjusted readiness using circadian and sleep homeostat terms."""

    def __init__(
        self,
        acrophase_hour: float = 15.0,
        decay_rate_per_hour: float = 0.4,
        recovery_rate_per_hour: float = 1.0,
    ) -> None:
        self.acrophase_hour = float(acrophase_hour)
        self.decay_rate_per_hour = float(decay_rate_per_hour)
        self.recovery_rate_per_hour = float(recovery_rate_per_hour)

    @staticmethod
    def _ensure_timezone_aware(value: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError("datetime value required")
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value

    def _circadian_component(self, current_time: datetime) -> float:
        hour = (
            current_time.hour
            + (current_time.minute / 60.0)
            + (current_time.second / 3600.0)
            + (current_time.microsecond / 3_600_000_000.0)
        )
        return math.cos((2.0 * math.pi * (hour - self.acrophase_hour)) / 24.0)

    def _homeostatic_component(
        self,
        sleep_history: List[Tuple[datetime, datetime]],
        current_time: datetime,
    ) -> float:
        if not sleep_history:
            return 0.65

        normalized: List[Tuple[datetime, datetime]] = []
        for window in sleep_history:
            if not isinstance(window, tuple) or len(window) != 2:
                raise ValueError("each sleep history item must be (sleep_start, sleep_end)")
            sleep_start = self._ensure_timezone_aware(window[0])
            sleep_end = self._ensure_timezone_aware(window[1])
            if sleep_end <= sleep_start:
                raise ValueError("sleep window end must be after start")
            if sleep_start >= current_time:
                continue
            normalized.append((sleep_start, min(sleep_end, current_time)))

        if not normalized:
            return 0.65

        normalized.sort(key=lambda item: item[0])

        merged: List[Tuple[datetime, datetime]] = []
        for interval in normalized:
            if not merged:
                merged.append(interval)
                continue
            last_start, last_end = merged[-1]
            start, end = interval
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append(interval)

        sleep_reservoir = 1.0
        cursor = merged[0][0]
        for sleep_start, sleep_end in merged:
            if sleep_start > cursor:
                awake_hours = (sleep_start - cursor).total_seconds() / 3600.0
                sleep_reservoir *= math.exp(-self.decay_rate_per_hour * max(0.0, awake_hours))
            sleep_hours = max(0.0, (sleep_end - sleep_start).total_seconds() / 3600.0)
            sleep_reservoir = 1.0 - (1.0 - sleep_reservoir) * math.exp(
                -self.recovery_rate_per_hour * sleep_hours
            )
            cursor = sleep_end

        if current_time > cursor:
            awake_hours = (current_time - cursor).total_seconds() / 3600.0
            sleep_reservoir *= math.exp(-self.decay_rate_per_hour * max(0.0, awake_hours))

        return max(0.0, min(1.0, sleep_reservoir))

    def compute_fatigue_score(
        self,
        sleep_history: List[Tuple[datetime, datetime]],
        current_time: datetime,
    ) -> float:
        """Return fatigue-adjusted readiness score (0-100, 100 fully rested)."""
        now = self._ensure_timezone_aware(current_time)
        circadian = self._circadian_component(now)
        homeostatic = self._homeostatic_component(sleep_history, now)
        combined = (circadian + homeostatic + 1.0) / 3.0
        score = max(0.0, min(100.0, combined * 100.0))
        return round(score, 2)
