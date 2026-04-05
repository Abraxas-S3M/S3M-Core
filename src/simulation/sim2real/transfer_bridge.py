"""
S3M Simulation-to-Real Transfer Bridge
======================================
Tracks and quantifies transfer risk between simulation and real-world
operation so deployment decisions preserve tactical reliability.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class TransferMetrics(BaseModel):
    """Metrics quantifying sim-to-real transfer gap."""

    metric_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    kl_divergence: float = 0.0
    js_divergence: float = 0.0
    performance_delta: float = 0.0  # real_perf - sim_perf (negative = degradation)
    calibration_error: float = 0.0
    domain_gap_score: float = 0.0  # 0=perfect transfer, 1=no transfer
    samples_sim: int = 0
    samples_real: int = 0


class GapAssessment(BaseModel):
    """Deployment-readiness assessment based on transfer metrics."""

    ready_for_deployment: bool = False
    overall_gap_score: float = 1.0
    recommendations: List[str] = Field(default_factory=list)
    recommendations_ar: List[str] = Field(default_factory=list)
    metrics: Optional[TransferMetrics] = None


class TransferBridge:
    """
    Measures transfer quality and recommends go/no-go posture.

    Workflow:
      record simulated and real outcomes, then call assess_transfer_gap().
    """

    def __init__(self, gap_threshold: float = 0.3) -> None:
        if gap_threshold <= 0.0 or gap_threshold > 1.0:
            raise ValueError("gap_threshold must be in (0, 1]")
        self._gap_threshold = gap_threshold
        self._sim_predictions: List[float] = []
        self._sim_labels: List[float] = []
        self._real_predictions: List[float] = []
        self._real_labels: List[float] = []
        self._history: List[TransferMetrics] = []

    def record_sim_performance(self, predictions: List[float], labels: List[float]) -> None:
        """Record simulation-domain predictions and labels."""
        self._append_records(self._sim_predictions, self._sim_labels, predictions, labels)

    def record_real_performance(self, predictions: List[float], labels: List[float]) -> None:
        """Record real-domain predictions and labels."""
        self._append_records(self._real_predictions, self._real_labels, predictions, labels)

    def assess_transfer_gap(self) -> GapAssessment:
        """Compute transfer metrics and deployment recommendation."""
        if not self._sim_predictions or not self._real_predictions:
            return GapAssessment(
                recommendations=["Insufficient data for assessment"],
                recommendations_ar=["Insufficient data for assessment"],
            )

        sim_acc = self._accuracy(self._sim_predictions, self._sim_labels)
        real_acc = self._accuracy(self._real_predictions, self._real_labels)
        perf_delta = real_acc - sim_acc

        kl = self._kl_divergence(self._sim_predictions, self._real_predictions)
        js = self._js_divergence(self._sim_predictions, self._real_predictions)
        cal_error = self._calibration_error(self._real_predictions, self._real_labels)

        gap_score = min(1.0, (abs(perf_delta) + js + cal_error) / 3.0)
        metrics = TransferMetrics(
            kl_divergence=kl,
            js_divergence=js,
            performance_delta=perf_delta,
            calibration_error=cal_error,
            domain_gap_score=gap_score,
            samples_sim=len(self._sim_predictions),
            samples_real=len(self._real_predictions),
        )
        self._history.append(metrics)

        recommendations = []
        recommendations_ar = []
        if gap_score > self._gap_threshold:
            recommendations.append("Domain gap too large for safe deployment")
            recommendations_ar.append("Domain gap too large for safe deployment")
        if abs(perf_delta) > 0.15:
            recommendations.append(
                "Significant real-domain performance drop observed; increase domain randomization"
            )
            recommendations_ar.append(
                "Significant real-domain performance drop observed; increase domain randomization"
            )
        if cal_error > 0.1:
            recommendations.append("Confidence calibration is weak; apply temperature scaling")
            recommendations_ar.append("Confidence calibration is weak; apply temperature scaling")
        if not recommendations:
            recommendations.append("Transfer quality acceptable for deployment")
            recommendations_ar.append("Transfer quality acceptable for deployment")

        return GapAssessment(
            ready_for_deployment=gap_score <= self._gap_threshold,
            overall_gap_score=gap_score,
            recommendations=recommendations,
            recommendations_ar=recommendations_ar,
            metrics=metrics,
        )

    def get_history(self) -> List[TransferMetrics]:
        return list(self._history)

    @staticmethod
    def _append_records(
        out_predictions: List[float],
        out_labels: List[float],
        predictions: List[float],
        labels: List[float],
    ) -> None:
        if not isinstance(predictions, list) or not isinstance(labels, list):
            raise TypeError("predictions and labels must be lists")
        n = min(len(predictions), len(labels))
        for i in range(n):
            pred = TransferBridge._clamp_unit_float(predictions[i])
            label = TransferBridge._clamp_unit_float(labels[i])
            out_predictions.append(pred)
            out_labels.append(label)

    @staticmethod
    def _accuracy(predictions: List[float], labels: List[float]) -> float:
        if not predictions or not labels:
            return 0.0
        n = min(len(predictions), len(labels))
        if n == 0:
            return 0.0
        correct = sum(1 for i in range(n) if (predictions[i] >= 0.5) == (labels[i] >= 0.5))
        return correct / n

    @staticmethod
    def _kl_divergence(p_samples: List[float], q_samples: List[float], bins: int = 20) -> float:
        """Approximate KL divergence using histogram binning."""
        if not p_samples or not q_samples:
            return 0.0
        eps = 1e-10
        all_vals = p_samples + q_samples
        lo = min(all_vals)
        hi = max(all_vals)
        if hi - lo < eps:
            return 0.0

        width = (hi - lo) / bins
        p_hist = [0.0] * bins
        q_hist = [0.0] * bins

        for value in p_samples:
            idx = min(int((value - lo) / width), bins - 1)
            p_hist[idx] += 1.0
        for value in q_samples:
            idx = min(int((value - lo) / width), bins - 1)
            q_hist[idx] += 1.0

        p_total = sum(p_hist) or 1.0
        q_total = sum(q_hist) or 1.0

        kl = 0.0
        for i in range(bins):
            p = (p_hist[i] / p_total) + eps
            q = (q_hist[i] / q_total) + eps
            kl += p * math.log(p / q)
        return max(0.0, kl)

    @staticmethod
    def _js_divergence(p_samples: List[float], q_samples: List[float]) -> float:
        """Symmetric Jensen-Shannon divergence estimate."""
        kl_pq = TransferBridge._kl_divergence(p_samples, q_samples)
        kl_qp = TransferBridge._kl_divergence(q_samples, p_samples)
        return (kl_pq + kl_qp) / 2.0

    @staticmethod
    def _calibration_error(predictions: List[float], labels: List[float], n_bins: int = 10) -> float:
        """Expected Calibration Error (ECE)."""
        if not predictions or not labels:
            return 0.0
        n = min(len(predictions), len(labels))
        if n == 0:
            return 0.0

        buckets: Dict[int, List[Tuple[float, float]]] = defaultdict(list)
        for i in range(n):
            bucket_idx = min(int(predictions[i] * n_bins), n_bins - 1)
            buckets[bucket_idx].append((predictions[i], labels[i]))

        ece = 0.0
        for entries in buckets.values():
            avg_conf = sum(pred for pred, _ in entries) / len(entries)
            avg_acc = sum(1.0 for _, label in entries if label >= 0.5) / len(entries)
            ece += abs(avg_conf - avg_acc) * len(entries) / n
        return ece

    @staticmethod
    def _clamp_unit_float(value: float) -> float:
        try:
            cast = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(cast):
            return 0.0
        return max(0.0, min(1.0, cast))
