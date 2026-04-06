"""Unit tests for cloud CPU promotion/metrics/resource control modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.training.cloud_cpu.contracts import CheckpointMeta, CycleMetrics, PromotionDecision
from src.training.cloud_cpu.metrics_store import MetricsStore
from src.training.cloud_cpu.promotion_gate import PromotionGate
from src.training.cloud_cpu.resource_guard import ResourceGuard, ThrottleAction


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_promotion_gate_passes_when_all_conditions_satisfied(tmp_path: Path) -> None:
    global_cfg = tmp_path / "promotion_gate.yaml"
    track_cfg = tmp_path / "track_gate.yaml"
    _write_yaml(
        global_cfg,
        """
promotion:
  min_steps: 100
  cooldown_steps: 50
  regression_tolerance: 0.03
""".strip(),
    )
    _write_yaml(
        track_cfg,
        """
promotion_thresholds:
  overall: 0.90
  fidelity: 0.80
""".strip(),
    )

    gate = PromotionGate(config_path=global_cfg, track_config_path=track_cfg)
    meta = CheckpointMeta(checkpoint_id="ckpt-001", track="nato", step=240, epoch=2)
    eval_results = {"overall": 0.93, "fidelity": 0.84}
    previous = {"step": 150, "eval_scores": {"overall": 0.92, "fidelity": 0.83}}

    decision = gate.evaluate(meta, eval_results, previous)

    assert decision.passed is True
    assert decision.reason == "All checks passed"
    assert decision.promoted_at is not None


def test_promotion_gate_reports_detailed_failures(tmp_path: Path) -> None:
    global_cfg = tmp_path / "promotion_gate.yaml"
    track_cfg = tmp_path / "track_gate.yaml"
    _write_yaml(
        global_cfg,
        """
promotion:
  min_steps: 500
  cooldown_steps: 200
  regression_tolerance: 0.01
""".strip(),
    )
    _write_yaml(
        track_cfg,
        """
promotion_thresholds:
  overall: 0.95
  fidelity: 0.90
""".strip(),
    )

    gate = PromotionGate(config_path=global_cfg, track_config_path=track_cfg)
    meta = CheckpointMeta(checkpoint_id="ckpt-002", track="saudi_mod", step=560, epoch=3)
    eval_results = {"overall": 0.92, "fidelity": 0.89}
    previous = {
        "step": 500,
        "promoted_at": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
        "eval_scores": {"overall": 0.95, "fidelity": 0.92},
    }
    # Add a strict time cooldown to force the timestamp check.
    gate = PromotionGate(config_path=global_cfg, track_config_path=track_cfg)
    gate._global_cfg["cooldown_seconds"] = 300

    decision = gate.evaluate(meta, eval_results, previous)

    assert decision.passed is False
    assert "cooldown active" in decision.reason
    assert "overall=0.9200 below threshold 0.9500" in decision.reason
    assert "regression on fidelity" in decision.reason


def test_metrics_store_writes_reads_and_summarizes(tmp_path: Path) -> None:
    store = MetricsStore(metrics_dir=tmp_path)
    store.write_cycle(
        CycleMetrics(
            track="nato",
            step=100,
            epoch=1,
            samples_processed=1_000,
            loss=1.0,
            eval_results={"overall": 0.80},
        )
    )
    store.write_cycle(
        CycleMetrics(
            track="nato",
            step=200,
            epoch=2,
            samples_processed=1_500,
            loss=0.8,
            eval_results={"overall": 0.88},
        )
    )
    store.write_promotion(
        PromotionDecision(
            checkpoint_id="ckpt-200",
            track="nato",
            passed=True,
            eval_scores={"overall": 0.88},
            thresholds={"overall": 0.85},
            promoted_at=datetime.now(timezone.utc).isoformat(),
            reason="All checks passed",
            regression_vs_previous={"overall": -0.02},
        )
    )

    latest = store.get_latest("nato", n=5)
    summary = store.get_track_summary("nato")
    kpis = store.get_demo_kpis("nato")

    assert len(latest) == 2
    assert latest[-1].step == 200
    assert summary["latest_step"] == 200
    assert summary["last_promotion"]["checkpoint_id"] == "ckpt-200"
    assert "trend" in summary
    assert kpis["status"] == "ok"
    assert kpis["kpis"]["promotions_passed"] == 1
    assert (tmp_path / "nato_cycles.jsonl").exists()
    assert (tmp_path / "promotions.jsonl").exists()


@pytest.mark.parametrize(
    ("cpu", "mem", "latency", "expected"),
    [
        (30.0, 40.0, None, ThrottleAction.NORMAL),
        (90.0, 40.0, None, ThrottleAction.REDUCE_BATCH),
        (40.0, 92.0, None, ThrottleAction.PAUSE),
        (40.0, 40.0, 700.0, ThrottleAction.EVAL_ONLY),
    ],
)
def test_resource_guard_action_recommendation(
    monkeypatch: pytest.MonkeyPatch,
    cpu: float,
    mem: float,
    latency: float | None,
    expected: ThrottleAction,
) -> None:
    guard = ResourceGuard(api_latency_target_ms=500.0)
    monkeypatch.setattr(guard, "_cpu_percent", lambda: cpu)
    monkeypatch.setattr(guard, "_memory_percent", lambda: mem)
    monkeypatch.setattr(guard, "_api_latency_ms", lambda: latency)

    status = guard.check()

    assert status.recommended_action == expected
    assert status.cpu_percent == cpu
    assert status.memory_percent == mem
