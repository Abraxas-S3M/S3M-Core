"""Geopolitical risk scoring for S3M regional awareness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from src.apps._shared import clamp, safe_float, utc_now_iso


class RiskScorer:
    """Track and update risk posture per region/topic."""

    def __init__(self) -> None:
        self._scores: Dict[str, dict] = {}
        self._last_decay_hours: float = 0.0
        self.risk_decay_per_hour: float = 1.0

    def _ensure_region(self, region: str) -> dict:
        if not isinstance(region, str) or not region.strip():
            raise ValueError("region must be a non-empty string")
        key = region.strip()
        if key not in self._scores:
            self._scores[key] = {
                "score": 0.0,
                "trend": "stable",
                "last_updated": utc_now_iso(),
                "history": [],
            }
        return self._scores[key]

    def _update_trend(self, record: dict) -> None:
        changes = [safe_float(h.get("delta", 0.0)) for h in record.get("history", [])][-5:]
        if not changes:
            record["trend"] = "stable"
            return
        avg = sum(changes) / len(changes)
        if avg > 0.2:
            record["trend"] = "rising"
        elif avg < -0.2:
            record["trend"] = "declining"
        else:
            record["trend"] = "stable"

    def update_score(self, region: str, delta: float, reason: str) -> None:
        """Adjust score and store auditable change history."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        record = self._ensure_region(region)
        new_score = clamp(safe_float(record.get("score", 0.0)) + safe_float(delta), 0.0, 100.0)
        history_entry = {
            "timestamp": utc_now_iso(),
            "delta": safe_float(delta),
            "reason": reason.strip(),
            "new_score": new_score,
        }
        record["score"] = new_score
        record["last_updated"] = history_entry["timestamp"]
        record.setdefault("history", []).append(history_entry)
        self._update_trend(record)

    def get_score(self, region: str) -> dict:
        """Return current score snapshot for one region."""
        record = self._ensure_region(region)
        return {
            "region": region.strip(),
            "score": record["score"],
            "trend": record["trend"],
            "last_updated": record["last_updated"],
            "history": list(record.get("history", [])),
        }

    def get_all_scores(self) -> Dict[str, dict]:
        """Return all tracked region scores."""
        return {region: self.get_score(region) for region in self._scores.keys()}

    def get_high_risk_regions(self, threshold: float = 70) -> List[dict]:
        """Return regions with risk score above threshold."""
        th = safe_float(threshold, 70.0)
        return [
            self.get_score(region)
            for region, record in self._scores.items()
            if safe_float(record.get("score", 0.0)) >= th
        ]

    def ingest_events(self, events: List[dict]) -> None:
        """Apply scoring heuristics for event streams."""
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        self.apply_decay(hours_elapsed=1.0)
        for event in events:
            if not isinstance(event, dict):
                continue
            region = str(event.get("region", "Unknown Region")).strip() or "Unknown Region"
            level = str(event.get("level", "")).upper()
            resolved = bool(event.get("resolved", False))
            positive = bool(event.get("positive_development", False))
            if resolved or positive:
                self.update_score(region, -5.0, "positive development / threat resolved")
                continue
            if level == "CRITICAL":
                self.update_score(region, 15.0, "critical threat event")
            elif level == "HIGH":
                self.update_score(region, 8.0, "high threat event")
            elif level == "MEDIUM":
                self.update_score(region, 3.0, "medium threat event")

    def apply_decay(self, hours_elapsed: float = 1.0) -> None:
        """Reduce all scores over time to model stabilization."""
        hours = max(0.0, safe_float(hours_elapsed, 1.0))
        self._last_decay_hours = hours
        if hours <= 0:
            return
        decay = hours * self.risk_decay_per_hour
        for region in list(self._scores.keys()):
            record = self._scores[region]
            old = safe_float(record.get("score", 0.0))
            new = clamp(old - decay, 0.0, 100.0)
            if new != old:
                record["score"] = new
                entry = {
                    "timestamp": utc_now_iso(),
                    "delta": -(old - new),
                    "reason": f"auto_decay_{hours:.2f}h",
                    "new_score": new,
                }
                record.setdefault("history", []).append(entry)
                record["last_updated"] = entry["timestamp"]
                self._update_trend(record)

    def export(self, filepath: str) -> None:
        """Export risk state for audit transfer in air-gapped operations."""
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": utc_now_iso(),
            "scores": self.get_all_scores(),
            "last_decay_hours": self._last_decay_hours,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
