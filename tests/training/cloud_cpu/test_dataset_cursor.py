"""Unit tests for cloud CPU DatasetCursor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, List

from src.training.cloud_cpu.dataset_cursor import DatasetCursor


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_scenario(
    scenarios_dir: Path,
    scenario_name: str,
    track: str,
    prompts: Iterable[str],
    labels: Iterable[str],
) -> Path:
    scenario_dir = scenarios_dir / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    prompt_lines: List[str] = [json.dumps({"prompt": item, "weight": 1.0}) for item in prompts]
    label_lines: List[str] = [json.dumps({"completion": item}) for item in labels]
    prompts_blob = "\n".join(prompt_lines) + "\n"
    labels_blob = "\n".join(label_lines) + "\n"

    (scenario_dir / "prompts.jsonl").write_text(prompts_blob, encoding="utf-8")
    (scenario_dir / "labels.jsonl").write_text(labels_blob, encoding="utf-8")
    manifest = {
        "scenario_id": scenario_name,
        "track": track,
        "data_class": "command",
        "checksums": {
            "prompts.jsonl": _sha256_text(prompts_blob),
            "labels.jsonl": _sha256_text(labels_blob),
        },
    }
    (scenario_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return scenario_dir


def test_cursor_reads_in_order_and_moves_processed(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    _write_scenario(
        scenarios,
        "scenario-00001",
        "saudi_mod",
        prompts=["alpha", "bravo", "charlie"],
        labels=["A", "B", "C"],
    )

    cursor = DatasetCursor("saudi_mod", scenarios, processed, rejected)
    first = cursor.next_batch(batch_size=2)
    assert [row.prompt for row in first] == ["alpha", "bravo"]
    assert cursor.get_cursor()["line_idx"] == 2

    second = cursor.next_batch(batch_size=2)
    assert [row.prompt for row in second] == ["charlie"]
    assert (processed / "scenario-00001").exists()
    assert not (scenarios / "scenario-00001").exists()


def test_cursor_rejects_invalid_checksum_pack(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    scenario_dir = _write_scenario(
        scenarios,
        "scenario-00001",
        "ukraine_mod",
        prompts=["good"],
        labels=["label"],
    )
    # Tamper after manifest write to trigger checksum failure.
    (scenario_dir / "prompts.jsonl").write_text('{"prompt":"tampered"}\n', encoding="utf-8")

    cursor = DatasetCursor("ukraine_mod", scenarios, processed, rejected)
    batch = cursor.next_batch(batch_size=1)
    assert batch == []
    assert (rejected / "scenario-00001").exists()


def test_cursor_restore_resumes_mid_scenario(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    processed = tmp_path / "processed"
    rejected = tmp_path / "rejected"
    _write_scenario(
        scenarios,
        "scenario-00001",
        "nato",
        prompts=["p1", "p2", "p3"],
        labels=["l1", "l2", "l3"],
    )

    cursor_a = DatasetCursor("nato", scenarios, processed, rejected)
    first = cursor_a.next_batch(batch_size=1)
    assert first[0].prompt == "p1"
    saved = cursor_a.get_cursor()

    cursor_b = DatasetCursor("nato", scenarios, processed, rejected)
    cursor_b.restore_cursor(saved)
    second = cursor_b.next_batch(batch_size=1)
    assert second[0].prompt == "p2"

