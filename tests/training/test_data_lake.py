"""Unit tests for domain-partitioned training data lake writes."""

from __future__ import annotations

import json
from pathlib import Path

from src.training import data_lake as data_lake_module
from src.training.data_lake import DataLake


def test_write_persists_record_to_domain_partition(tmp_path: Path) -> None:
    lake = DataLake(base_dir=tmp_path, max_file_size_bytes=1024, source="gui_bridge")

    target = lake.write("comms", "request payload", "response payload", language="en")

    assert target == tmp_path / "comms" / "part-000001.jsonl"
    assert target.exists()
    row = json.loads(target.read_text(encoding="utf-8").strip())
    assert row["domain"] == "comms"
    assert row["input"] == "request payload"
    assert row["output"] == "response payload"
    assert row["language"] == "en"
    assert row["source"] == "gui_bridge"


def test_write_rotates_and_runs_dvc_add(monkeypatch, tmp_path: Path) -> None:
    dvc_calls: list[tuple[list[str], dict]] = []

    def _fake_run(command: list[str], **kwargs):
        dvc_calls.append((command, kwargs))

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(data_lake_module.subprocess, "run", _fake_run)
    lake = DataLake(base_dir=tmp_path, max_file_size_bytes=1)

    first_path = lake.write("planning", "A", "B")
    second_path = lake.write("planning", "C", "D")

    assert first_path == tmp_path / "planning" / "part-000001.jsonl"
    assert second_path == tmp_path / "planning" / "part-000002.jsonl"
    assert len(dvc_calls) == 1
    assert dvc_calls[0][0] == ["dvc", "add", str(first_path)]
    assert Path(dvc_calls[0][1]["cwd"]) == tmp_path


def test_write_succeeds_when_dvc_add_fails(monkeypatch, tmp_path: Path) -> None:
    def _raise_runtime_error(*args, **kwargs):
        raise RuntimeError("dvc unavailable")

    monkeypatch.setattr(data_lake_module.subprocess, "run", _raise_runtime_error)
    lake = DataLake(base_dir=tmp_path, max_file_size_bytes=1)

    lake.write("surveillance", "first", "record")
    second_path = lake.write("surveillance", "second", "record")

    assert second_path == tmp_path / "surveillance" / "part-000002.jsonl"
    assert second_path.exists()
