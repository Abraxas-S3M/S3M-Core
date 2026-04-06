"""Persistent metrics store for cloud CPU training progress.

Military/tactical context:
Field and command demos require stable KPI history from offline training cycles.
This store records append-only JSONL metrics so readiness dashboards can report
training health, quality drift, and promotion cadence without remote services.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from src.training.cloud_cpu.contracts import CycleMetrics, PromotionDecision

logger = logging.getLogger("s3m.training.cloud_cpu.metrics_store")


class MetricsStore:
    """Append-only JSONL persistence for cycle and promotion records."""

    def __init__(self, metrics_dir: Path) -> None:
        self._dir = metrics_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def write_cycle(self, metrics: CycleMetrics) -> None:
        """Persist one training cycle record for a track."""
        payload = metrics.model_dump() if hasattr(metrics, "model_dump") else dict(metrics)
        track = str(payload.get("track", "unknown"))
        path = self._dir / f"{track}_cycles.jsonl"
        self._append_jsonl(path, payload)

    def write_promotion(self, decision: PromotionDecision) -> None:
        """Persist one promotion decision record."""
        payload = decision.model_dump() if hasattr(decision, "model_dump") else dict(decision)
        path = self._dir / "promotions.jsonl"
        self._append_jsonl(path, payload)

    def get_latest(self, track: str, n: int = 100) -> List[CycleMetrics]:
        """Return the latest N cycle metrics for the specified track."""
        path = self._dir / f"{track}_cycles.jsonl"
        records = self._tail_jsonl(path, max(1, int(n)))
        return [CycleMetrics.model_validate(record) for record in records]

    def get_track_summary(self, track: str) -> Dict[str, Any]:
        """Summarize latest track status and trend indicators."""
        cycles = self.get_latest(track, 200)
        promotions = self._get_promotions(track=track, n=100)
        if not cycles:
            return {
                "track": track,
                "status": "no_data",
                "latest_step": 0,
                "latest_epoch": 0,
                "samples": 0,
                "last_eval": {},
                "last_promotion": None,
                "trend": "unknown",
            }

        latest = cycles[-1]
        total_samples = sum(max(0, int(c.samples_processed)) for c in cycles)
        losses = [float(c.loss) for c in cycles if isinstance(c.loss, (int, float))]
        trend = self._compute_loss_trend(losses)

        last_eval = latest.eval_results or {}
        last_promotion = promotions[-1] if promotions else None

        return {
            "track": track,
            "status": "active",
            "latest_step": int(latest.step),
            "latest_epoch": int(latest.epoch),
            "samples": total_samples,
            "last_eval": last_eval,
            "last_promotion": last_promotion,
            "trend": trend,
        }

    def get_demo_kpis(self, track: str) -> Dict[str, Any]:
        """Return demo-ready KPI payload aligned to training-readiness reporting."""
        cycles = self.get_latest(track, 500)
        promotions = self._get_promotions(track=track, n=200)
        passed_promotions = [p for p in promotions if bool(p.get("passed"))]
        if not cycles:
            return {
                "track": track,
                "status": "awaiting_data",
                "kpis": {},
            }

        latest = cycles[-1]
        latest_eval = latest.eval_results or {}
        losses = [float(c.loss) for c in cycles if isinstance(c.loss, (int, float))]
        trend = self._compute_loss_trend(losses)

        previous_window = cycles[-48:-24] if len(cycles) >= 48 else []
        current_window = cycles[-24:] if len(cycles) >= 24 else cycles

        def _window_mean(window: List[CycleMetrics], metric: str) -> Optional[float]:
            scores = [
                float(c.eval_results.get(metric))
                for c in window
                if isinstance(c.eval_results.get(metric), (int, float))
            ]
            return mean(scores) if scores else None

        overall_yesterday = _window_mean(previous_window, "overall")
        overall_today = _window_mean(current_window, "overall")

        readiness_state = "warming"
        if passed_promotions:
            readiness_state = "promotion_ready"
        if len(passed_promotions) >= 3 and trend in {"stable", "improving"}:
            readiness_state = "demo_stable"

        return {
            "track": track,
            "status": "ok",
            "readiness": readiness_state,
            "kpis": {
                "total_training_steps": int(latest.step),
                "total_epochs": int(latest.epoch),
                "total_samples_processed": sum(max(0, int(c.samples_processed)) for c in cycles),
                "current_loss": round(float(latest.loss), 6),
                "loss_trend": trend,
                "latest_eval": latest_eval,
                "promotions_passed": len(passed_promotions),
                "promotions_total": len(promotions),
                "overall_score_yesterday": round(overall_yesterday, 6) if overall_yesterday else None,
                "overall_score_today": round(overall_today, 6) if overall_today else None,
            },
        }

    def _get_promotions(self, track: Optional[str], n: int) -> List[Dict[str, Any]]:
        path = self._dir / "promotions.jsonl"
        records = self._tail_jsonl(path, max(1, int(n * 4)))
        if track:
            records = [row for row in records if row.get("track") == track]
        return records[-n:]

    @staticmethod
    def _compute_loss_trend(losses: List[float]) -> str:
        if len(losses) < 8:
            return "insufficient_data"
        split = max(1, len(losses) // 2)
        earlier = mean(losses[:split])
        recent = mean(losses[split:])
        if recent <= earlier * 0.97:
            return "improving"
        if recent >= earlier * 1.03:
            return "degrading"
        return "stable"

    @staticmethod
    def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str, ensure_ascii=True) + "\n")

    @staticmethod
    def _tail_jsonl(path: Path, n: int) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        records: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    item = line.strip()
                    if not item:
                        continue
                    try:
                        parsed = json.loads(item)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed JSONL line in %s", path)
                        continue
                    if isinstance(parsed, dict):
                        records.append(parsed)
        except OSError:
            return []
        return records[-n:]
