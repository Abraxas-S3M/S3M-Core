"""Eval-gated checkpoint promotion for cloud CPU training.

Military/tactical context:
Only validated checkpoints are allowed to move into the live demo path.
This prevents visible quality regressions during command-brief scenarios where
operator trust in model output must remain stable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from src.training.cloud_cpu.contracts import CheckpointMeta, PromotionDecision

logger = logging.getLogger("s3m.training.cloud_cpu.promotion_gate")


class PromotionGate:
    """Decides whether an evaluated checkpoint can be promoted."""

    def __init__(
        self,
        config_path: Path | str = "configs/training/promotion_gate.yaml",
        track_config_path: Optional[Path | str] = None,
    ) -> None:
        self._global_cfg = self._normalize_promotion_config(self._load_yaml(config_path))
        self._track_cfg = self._load_yaml(track_config_path)

    def evaluate(
        self,
        checkpoint_meta: CheckpointMeta,
        eval_results: Dict[str, float],
        last_promoted_results: Optional[Dict[str, Any]] = None,
    ) -> PromotionDecision:
        """Run promotion checks and return a decision with detailed rationale."""
        track = str(self._read_field(checkpoint_meta, "track", "unknown"))
        step = int(self._read_field(checkpoint_meta, "step", 0))
        checkpoint_id = str(self._read_field(checkpoint_meta, "checkpoint_id", ""))

        cfg = self._merged_track_config(track)
        thresholds = self._extract_thresholds(cfg, track)

        reasons: list[str] = []

        # Check 1: minimum training steps before promotion attempts.
        min_steps = int(
            cfg.get(
                "min_steps",
                cfg.get(
                    "min_steps_before_first_promotion",
                    cfg.get("min_steps_before_promotion", 0),
                ),
            )
        )
        if step < min_steps:
            reasons.append(f"step {step} is below minimum required {min_steps}")

        # Check 2: cooldown between promotions (supports step and timestamp windows).
        cooldown_steps = int(cfg.get("cooldown_steps", cfg.get("min_steps_between_promotions", 0)))
        cooldown_seconds = int(cfg.get("cooldown_seconds", 0))
        last_step = self._extract_last_promoted_step(last_promoted_results)
        if cooldown_steps > 0 and last_step is not None:
            since_last = step - last_step
            if since_last < cooldown_steps:
                reasons.append(
                    f"cooldown active: only {since_last} steps since last promotion "
                    f"(requires {cooldown_steps})"
                )

        last_promoted_at = self._extract_last_promoted_time(last_promoted_results)
        if cooldown_seconds > 0 and last_promoted_at is not None:
            elapsed = (datetime.now(timezone.utc) - last_promoted_at).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = int(max(0.0, cooldown_seconds - elapsed))
                reasons.append(f"cooldown active: {remaining}s remaining before next promotion")

        # Check 3: all configured thresholds must pass.
        threshold_failures = self._threshold_failures(eval_results, thresholds)
        reasons.extend(threshold_failures)

        # Check 4: guard against regressions vs last promoted checkpoint.
        regression_tolerance = float(cfg.get("regression_tolerance", 0.0))
        regressions = self._compute_regressions(last_promoted_results, eval_results)
        for metric_name, drop in regressions.items():
            if drop > regression_tolerance:
                prev = self._extract_previous_scores(last_promoted_results).get(metric_name, 0.0)
                curr = float(eval_results.get(metric_name, 0.0))
                reasons.append(
                    f"regression on {metric_name}: {prev:.4f} -> {curr:.4f} "
                    f"(drop {drop:.4f} > tolerance {regression_tolerance:.4f})"
                )

        passed = len(reasons) == 0
        reason = "All checks passed" if passed else "; ".join(reasons)

        return PromotionDecision(
            checkpoint_id=checkpoint_id,
            track=track,
            passed=passed,
            eval_scores={k: float(v) for k, v in eval_results.items()},
            thresholds=thresholds,
            promoted_at=datetime.now(timezone.utc).isoformat() if passed else None,
            reason=reason,
            regression_vs_previous=regressions,
        )

    @staticmethod
    def _read_field(source: Any, field: str, default: Any = None) -> Any:
        if isinstance(source, Mapping):
            return source.get(field, default)
        return getattr(source, field, default)

    @staticmethod
    def _load_yaml(path: Optional[Path | str]) -> Dict[str, Any]:
        if not path:
            return {}
        target = Path(path)
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _normalize_promotion_config(raw_cfg: Dict[str, Any]) -> Dict[str, Any]:
        promotion_cfg = raw_cfg.get("promotion")
        if isinstance(promotion_cfg, dict):
            return promotion_cfg
        return raw_cfg

    def _merged_track_config(self, track: str) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(self._global_cfg)
        track_cfg = self._track_cfg
        if not isinstance(track_cfg, dict):
            return merged

        scoped_cfg: Dict[str, Any] = {}
        if isinstance(track_cfg.get("promotion"), dict):
            scoped_cfg.update(track_cfg["promotion"])
        else:
            scoped_cfg.update(track_cfg)

        tracks_cfg = scoped_cfg.get("tracks")
        if isinstance(tracks_cfg, dict) and isinstance(tracks_cfg.get(track), dict):
            merged.update(scoped_cfg)
            merged.update(tracks_cfg[track])
            return merged

        merged.update(scoped_cfg)
        return merged

    @staticmethod
    def _extract_thresholds(cfg: Dict[str, Any], track: str) -> Dict[str, float]:
        raw_thresholds = cfg.get("promotion_thresholds", {})
        if isinstance(raw_thresholds, dict):
            if track in raw_thresholds and isinstance(raw_thresholds[track], dict):
                raw_thresholds = raw_thresholds[track]
            return {
                str(metric): float(value)
                for metric, value in raw_thresholds.items()
                if isinstance(value, (int, float))
            }
        return {}

    @staticmethod
    def _threshold_failures(eval_results: Dict[str, float], thresholds: Dict[str, float]) -> list[str]:
        failures: list[str] = []
        for metric_name, threshold in thresholds.items():
            score = eval_results.get(metric_name)
            if score is None:
                failures.append(f"{metric_name} missing from eval results (required >= {threshold:.4f})")
                continue
            numeric_score = float(score)
            if numeric_score < threshold:
                failures.append(f"{metric_name}={numeric_score:.4f} below threshold {threshold:.4f}")
        return failures

    @staticmethod
    def _extract_previous_scores(last_promoted_results: Optional[Dict[str, Any]]) -> Dict[str, float]:
        if not last_promoted_results or not isinstance(last_promoted_results, dict):
            return {}
        if isinstance(last_promoted_results.get("eval_scores"), dict):
            source = last_promoted_results["eval_scores"]
        else:
            source = last_promoted_results
        return {
            str(metric): float(value)
            for metric, value in source.items()
            if isinstance(value, (int, float))
        }

    def _compute_regressions(
        self,
        last_promoted_results: Optional[Dict[str, Any]],
        eval_results: Dict[str, float],
    ) -> Dict[str, float]:
        previous_scores = self._extract_previous_scores(last_promoted_results)
        regressions: Dict[str, float] = {}
        for metric_name, old_score in previous_scores.items():
            if metric_name not in eval_results:
                continue
            drop = float(old_score) - float(eval_results[metric_name])
            regressions[metric_name] = round(drop, 6)
        return regressions

    @staticmethod
    def _extract_last_promoted_step(last_promoted_results: Optional[Dict[str, Any]]) -> Optional[int]:
        if not last_promoted_results:
            return None
        for key in ("step", "last_promoted_step", "promoted_step", "checkpoint_step"):
            value = last_promoted_results.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    @staticmethod
    def _extract_last_promoted_time(
        last_promoted_results: Optional[Dict[str, Any]],
    ) -> Optional[datetime]:
        if not last_promoted_results:
            return None
        for key in ("promoted_at", "timestamp", "last_promoted_at"):
            value = last_promoted_results.get(key)
            if not isinstance(value, str) or not value:
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
