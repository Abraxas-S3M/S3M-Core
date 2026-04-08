"""Risk score forecasting with optional Prophet and offline fallback logic.

This module keeps tactical risk history in a local SQLite operational store so
forecasting remains available in disconnected edge deployments.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sqlite3
from typing import Dict, List, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    from prophet import Prophet as _Prophet
except Exception:  # pragma: no cover - fallback path covered by tests
    _Prophet = None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


class OperationalStore:
    """SQLite-backed operational history store for risk scoring."""

    def __init__(self, db_path: str | None = None) -> None:
        configured = db_path or os.environ.get(
            "S3M_OPERATIONAL_STORE_DB",
            "/tmp/s3m_operational_store.sqlite3",
        )
        self._db_path = str(configured)
        parent = Path(self._db_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_history (
                    ts TEXT PRIMARY KEY,
                    score REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_risk_history_ts
                ON risk_history (ts)
                """
            )
            conn.commit()

    def append_risk_score(self, timestamp: datetime, score: float) -> None:
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be a datetime instance")
        if not isinstance(score, (float, int)):
            raise ValueError("score must be numeric")
        numeric_score = float(score)
        if not math.isfinite(numeric_score):
            raise ValueError("score must be finite")
        ts = _ensure_utc(timestamp).isoformat()
        bounded = _clamp_score(numeric_score)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO risk_history (ts, score) VALUES (?, ?)",
                (ts, bounded),
            )
            conn.commit()

    def get_recent_risk_scores(self, limit: int = 512) -> List[Tuple[datetime, float]]:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, score FROM risk_history ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()

        output: List[Tuple[datetime, float]] = []
        for ts_raw, score_raw in reversed(rows):
            try:
                ts = _ensure_utc(datetime.fromisoformat(str(ts_raw)))
                score = float(score_raw)
            except Exception:
                continue
            output.append((ts, _clamp_score(score)))
        return output


class RiskForecaster:
    """Forecast risk trajectory for near-term tactical planning horizons."""

    def __init__(self, store: OperationalStore | None = None, max_history: int = 720) -> None:
        self._store = store or OperationalStore()
        self._max_history = max(24, int(max_history))

    def forecast(
        self,
        historical_scores: List[Tuple[datetime, float]],
        horizon_hours: int = 24,
    ) -> List[float]:
        if not isinstance(horizon_hours, int) or horizon_hours <= 0:
            raise ValueError("horizon_hours must be a positive integer")

        normalized = self._normalize_history(historical_scores)
        for ts, score in normalized:
            self._store.append_risk_score(ts, score)
        persisted = self._store.get_recent_risk_scores(limit=self._max_history)

        if _Prophet is not None and len(persisted) >= 3:
            try:
                return self._prophet_forecast(persisted, horizon_hours=horizon_hours)
            except Exception:
                # Tactical continuity: keep forecasting active even if Prophet fails.
                pass
        return self._linear_extrapolation(persisted, horizon_hours=horizon_hours)

    def _normalize_history(
        self, historical_scores: Sequence[Tuple[datetime, float]]
    ) -> List[Tuple[datetime, float]]:
        if not isinstance(historical_scores, Sequence):
            raise ValueError("historical_scores must be a sequence")

        deduped: Dict[datetime, float] = {}
        for item in historical_scores:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("each historical point must be a (datetime, score) tuple")
            ts_raw, score_raw = item
            if not isinstance(ts_raw, datetime):
                raise ValueError("historical timestamp must be datetime")
            if not isinstance(score_raw, (float, int)):
                raise ValueError("historical score must be numeric")
            numeric = float(score_raw)
            if not math.isfinite(numeric):
                raise ValueError("historical score must be finite")
            deduped[_ensure_utc(ts_raw)] = _clamp_score(numeric)

        ordered = sorted(deduped.items(), key=lambda item: item[0])
        if len(ordered) > self._max_history:
            return ordered[-self._max_history :]
        return ordered

    def _prophet_forecast(
        self, historical_scores: List[Tuple[datetime, float]], horizon_hours: int
    ) -> List[float]:
        import pandas as pd

        frame = pd.DataFrame(
            {
                "ds": [ts for ts, _ in historical_scores],
                "y": [score for _, score in historical_scores],
            }
        )
        model = _Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
        )
        model.fit(frame)
        future = model.make_future_dataframe(
            periods=horizon_hours,
            freq="h",
            include_history=False,
        )
        predicted = model.predict(future)
        values = [_clamp_score(float(value)) for value in predicted["yhat"].tolist()]
        if len(values) < horizon_hours:
            values.extend([values[-1] if values else 50.0] * (horizon_hours - len(values)))
        return values[:horizon_hours]

    def _linear_extrapolation(
        self,
        historical_scores: List[Tuple[datetime, float]],
        horizon_hours: int,
    ) -> List[float]:
        if not historical_scores:
            return [50.0 for _ in range(horizon_hours)]
        if len(historical_scores) == 1:
            return [_clamp_score(historical_scores[-1][1]) for _ in range(horizon_hours)]

        window = historical_scores[-24:]
        base_time = window[0][0]
        x_values: List[float] = []
        y_values: List[float] = []
        for ts, score in window:
            elapsed = (ts - base_time).total_seconds() / 3600.0
            x_values.append(max(0.0, elapsed))
            y_values.append(_clamp_score(score))

        mean_x = sum(x_values) / len(x_values)
        mean_y = sum(y_values) / len(y_values)
        denominator = sum((x - mean_x) ** 2 for x in x_values)
        if denominator <= 0.0:
            slope = 0.0
        else:
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
            slope = numerator / denominator
        intercept = mean_y - slope * mean_x
        last_x = x_values[-1]

        return [
            _clamp_score(intercept + slope * (last_x + float(step + 1)))
            for step in range(horizon_hours)
        ]
