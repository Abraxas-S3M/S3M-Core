from __future__ import annotations

import json

from src.training.cloud_cpu.metrics_store import MetricsStore


def _append_jsonl(path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            if isinstance(row, str):
                handle.write(f"{row}\n")
            else:
                handle.write(f"{json.dumps(row)}\n")


def test_get_latest_returns_tail_records(tmp_path) -> None:
    metrics_dir = tmp_path / "metrics"
    store = MetricsStore(metrics_dir)
    _append_jsonl(
        metrics_dir / "saudi_mod.jsonl",
        [{"cycle": 1, "loss": 0.7}, {"cycle": 2, "loss": 0.5}, {"cycle": 3, "loss": 0.4}],
    )

    rows = store.get_latest("saudi_mod", 2)
    assert [row["cycle"] for row in rows] == [2, 3]


def test_track_summary_handles_missing_and_invalid_lines(tmp_path) -> None:
    metrics_dir = tmp_path / "metrics"
    store = MetricsStore(metrics_dir)
    _append_jsonl(
        metrics_dir / "nato.jsonl",
        [
            {"cycle": 10, "loss": 0.12, "status": "active", "timestamp": "2026-01-01T00:00:00Z"},
            "not-json",
            {"cycle": 11, "loss": 0.1, "status": "active", "timestamp": "2026-01-01T01:00:00Z"},
        ],
    )

    summary = store.get_track_summary("nato")
    assert summary["samples"] == 2
    assert summary["last_cycle"] == 11
    assert summary["avg_loss"] == 0.11

    idle = store.get_track_summary("ukraine_mod")
    assert idle["status"] == "idle"
    assert idle["samples"] == 0


def test_demo_kpis_returns_leadership_view(tmp_path) -> None:
    metrics_dir = tmp_path / "metrics"
    store = MetricsStore(metrics_dir)
    _append_jsonl(
        metrics_dir / "ukraine_mod.jsonl",
        [
            {"cycle": 1, "accuracy": 0.62, "timestamp": "2026-01-01T00:00:00Z"},
            {"cycle": 2, "accuracy": 0.71, "timestamp": "2026-01-01T01:00:00Z"},
        ],
    )

    kpis = store.get_demo_kpis("ukraine_mod")
    assert kpis["cycles_completed"] == 2
    assert kpis["last_accuracy"] == 0.71
    assert isinstance(kpis["readiness_score"], float)
