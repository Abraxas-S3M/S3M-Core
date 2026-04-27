"""Tests for Saudi training packet generation script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.training.generate_saudi_packets import DATA_CLASSES, generate_packets


def _read_jsonl(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    return rows


def _word_count(text: str) -> int:
    return len(text.replace("\n", " ").split())


def test_generate_packets_writes_expected_files_and_schema(tmp_path: Path) -> None:
    summary = generate_packets(output_dir=tmp_path, examples_per_class=5)

    assert set(summary) == {"command.jsonl", "cop_intel.jsonl", "risk_readiness.jsonl", "bilingual.jsonl"}
    assert all(count == 5 for count in summary.values())

    for data_class in DATA_CLASSES:
        output_path = tmp_path / f"{data_class}.jsonl"
        assert output_path.exists()
        rows = _read_jsonl(output_path)
        assert len(rows) == 5
        for row in rows:
            assert set(row) == {"prompt", "completion"}
            assert row["prompt"]
            wc = _word_count(row["completion"])
            assert 200 <= wc <= 400


@pytest.mark.parametrize(
    ("data_class", "required_sections"),
    [
        ("command", ["SITUATION:", "ASSESSMENT:", "RECOMMENDATION:", "RISK:"]),
        ("cop_intel", ["SOURCE CLASSIFICATION:", "CONFIDENCE LEVEL:", "INDICATOR LIST:", "ASSESSED INTENT:"]),
        (
            "risk_readiness",
            [
                "THREAT LEVEL:",
                "PROBABILITY (%):",
                "IMPACT (LOW/MEDIUM/HIGH/CRITICAL):",
                "TIME HORIZON:",
                "INDICATORS:",
                "RECOMMENDED MITIGATIONS:",
            ],
        ),
        ("bilingual", ["ARABIC SECTION (العربية):", "ENGLISH SECTION:"]),
    ],
)
def test_generate_packets_contains_expected_sections(
    tmp_path: Path,
    data_class: str,
    required_sections: list[str],
) -> None:
    generate_packets(output_dir=tmp_path, examples_per_class=3)
    rows = _read_jsonl(tmp_path / f"{data_class}.jsonl")
    assert len(rows) == 3
    for row in rows:
        completion = row["completion"]
        for marker in required_sections:
            assert marker in completion


def test_cli_execution_prints_summary(tmp_path: Path) -> None:
    cmd = [
        sys.executable,
        "scripts/training/generate_saudi_packets.py",
        "--output-dir",
        str(tmp_path),
        "--examples-per-class",
        "2",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=Path.cwd())

    assert result.returncode == 0, result.stderr
    assert "Generated saudi_mod training packets in" in result.stdout
    for name in ("command.jsonl", "cop_intel.jsonl", "risk_readiness.jsonl", "bilingual.jsonl"):
        assert f"{name}: 2 examples" in result.stdout
