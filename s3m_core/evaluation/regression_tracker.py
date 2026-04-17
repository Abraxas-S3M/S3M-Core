"""Regression tracking across model versions for tactical readiness metrics.

Military/tactical context:
Model updates must not degrade mission-critical behaviors. This tracker keeps
versioned metrics in durable local storage and flags regressions before field
deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Regression:
    """Represents one metric regression between two model versions."""

    metric_name: str
    baseline_value: float
    new_value: float
    delta: float
    severity: str


class RegressionTracker:
    """Track metrics over model versions and detect regressions."""

    def __init__(self, storage_dir: str | Path = "/tmp/s3m_regression_tracker") -> None:
        self._storage_dir = Path(storage_dir)
        self._jsonl_dir = self._storage_dir / "jsonl_metrics"
        self._db_path = self._storage_dir / "regression_metrics.sqlite3"
        self._jsonl_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def record(self, model_version: str, metrics: Dict[str, float]) -> None:
        """Persist metric values for a model version."""

        if not isinstance(model_version, str) or not model_version.strip():
            raise ValueError("model_version must be a non-empty string")
        if not isinstance(metrics, dict) or not metrics:
            raise ValueError("metrics must be a non-empty dictionary")

        now = datetime.now(timezone.utc).isoformat()
        normalized_version = model_version.strip()
        normalized_metrics: Dict[str, float] = {}
        for metric_name, metric_value in metrics.items():
            if not isinstance(metric_name, str) or not metric_name.strip():
                raise ValueError("metric names must be non-empty strings")
            if isinstance(metric_value, bool) or not isinstance(metric_value, (int, float)):
                raise ValueError(f"metric '{metric_name}' must be numeric")
            numeric = float(metric_value)
            if not math.isfinite(numeric):
                raise ValueError(f"metric '{metric_name}' must be finite")
            normalized_metrics[metric_name.strip()] = numeric

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO metric_history(metric_name, model_version, metric_value, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (metric_name, normalized_version, value, now)
                    for metric_name, value in normalized_metrics.items()
                ],
            )
            conn.commit()

        for metric_name, value in normalized_metrics.items():
            payload = {
                "metric_name": metric_name,
                "model_version": normalized_version,
                "metric_value": value,
                "recorded_at": now,
            }
            path = self._jsonl_dir / f"{self._sanitize_metric_name(metric_name)}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def check_regression(
        self,
        new_version: str,
        baseline_version: str,
        threshold: float = 0.05,
    ) -> List[Regression]:
        """Return metrics where the new version regressed beyond threshold."""

        if not isinstance(new_version, str) or not new_version.strip():
            raise ValueError("new_version must be a non-empty string")
        if not isinstance(baseline_version, str) or not baseline_version.strip():
            raise ValueError("baseline_version must be a non-empty string")
        if not isinstance(threshold, (int, float)) or threshold < 0.0:
            raise ValueError("threshold must be a non-negative float")

        baseline_metrics = self._get_metrics_for_version(baseline_version.strip())
        new_metrics = self._get_metrics_for_version(new_version.strip())
        regressions: List[Regression] = []

        for metric_name in sorted(set(baseline_metrics).intersection(new_metrics)):
            baseline_value = baseline_metrics[metric_name]
            new_value = new_metrics[metric_name]
            delta = new_value - baseline_value
            relative_drop = self._relative_drop(baseline_value, new_value)
            if relative_drop > float(threshold):
                regressions.append(
                    Regression(
                        metric_name=metric_name,
                        baseline_value=baseline_value,
                        new_value=new_value,
                        delta=round(delta, 6),
                        severity=self._severity_from_drop(relative_drop),
                    )
                )

        return sorted(
            regressions,
            key=lambda item: (self._severity_rank(item.severity), abs(item.delta)),
            reverse=True,
        )

    def get_trend(self, metric_name: str, last_n_versions: int = 10) -> List[Tuple[str, float]]:
        """Get recent metric trend as (model_version, metric_value)."""

        if not isinstance(metric_name, str) or not metric_name.strip():
            raise ValueError("metric_name must be a non-empty string")
        if not isinstance(last_n_versions, int) or last_n_versions <= 0:
            raise ValueError("last_n_versions must be a positive integer")

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT history.model_version, history.metric_value, history.id
                FROM metric_history AS history
                JOIN (
                    SELECT model_version, MAX(id) AS latest_id
                    FROM metric_history
                    WHERE metric_name = ?
                    GROUP BY model_version
                ) AS latest
                    ON history.id = latest.latest_id
                ORDER BY history.id DESC
                LIMIT ?
                """,
                (metric_name.strip(), last_n_versions),
            ).fetchall()

        ordered = list(reversed(rows))
        return [(str(version), float(value)) for version, value, _ in ordered]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False)

    def _init_schema(self) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metric_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_metric_history_name_version
                ON metric_history(metric_name, model_version, id DESC)
                """
            )
            conn.commit()

    def _get_metrics_for_version(self, model_version: str) -> Dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT history.metric_name, history.metric_value
                FROM metric_history AS history
                JOIN (
                    SELECT metric_name, MAX(id) AS latest_id
                    FROM metric_history
                    WHERE model_version = ?
                    GROUP BY metric_name
                ) AS latest
                    ON history.id = latest.latest_id
                """,
                (model_version,),
            ).fetchall()
        return {str(name): float(value) for name, value in rows}

    def _relative_drop(self, baseline_value: float, new_value: float) -> float:
        if math.isclose(baseline_value, 0.0, abs_tol=1e-9):
            return max(0.0, baseline_value - new_value)
        return max(0.0, (baseline_value - new_value) / abs(baseline_value))

    def _severity_from_drop(self, relative_drop: float) -> str:
        if relative_drop >= 0.4:
            return "critical"
        if relative_drop >= 0.2:
            return "high"
        if relative_drop >= 0.1:
            return "medium"
        return "low"

    def _severity_rank(self, severity: str) -> int:
        ranking = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return ranking.get(severity, 0)

    def _sanitize_metric_name(self, metric_name: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in metric_name)
        collapsed = cleaned.strip("_")
        return collapsed or "metric"
