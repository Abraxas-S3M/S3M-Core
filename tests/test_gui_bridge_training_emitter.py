"""Unit tests for GUI bridge training data emission."""

from __future__ import annotations

import json
from pathlib import Path

from src.api.gui_bridge import training_emitter


def test_emit_training_record_writes_jsonl(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(training_emitter, "TRAINING_DATA_DIR", tmp_path)

    training_emitter.emit_training_record(
        "command",
        {"query": "operational_context"},
        {"status": "ok", "tracks": 3},
        language="en",
    )

    target = tmp_path / "command" / "part-000001.jsonl"
    assert target.exists()
    row = json.loads(target.read_text(encoding="utf-8").strip())
    assert row["domain"] == "command"
    assert row["source"] == "gui_bridge"
    assert json.loads(row["input"]) == {"query": "operational_context"}
    assert json.loads(row["output"]) == {"status": "ok", "tracks": 3}


def test_emit_training_record_sanitizes_domain_and_normalizes_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(training_emitter, "TRAINING_DATA_DIR", tmp_path)

    class _Payload:
        def __init__(self, value: str) -> None:
            self.value = value

    training_emitter.emit_training_record(
        "../risk",
        {"query": _Payload("metrics")},
        {"items": [_Payload("alpha"), _Payload("bravo")]},
    )

    target = tmp_path / "risk" / "part-000001.jsonl"
    assert target.exists()
    row = json.loads(target.read_text(encoding="utf-8").strip())
    assert row["domain"] == "risk"
    assert json.loads(row["input"]) == {"query": {"value": "metrics"}}
    assert json.loads(row["output"]) == {"items": [{"value": "alpha"}, {"value": "bravo"}]}


def test_emit_training_record_never_raises_when_write_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(training_emitter, "TRAINING_DATA_DIR", tmp_path)

    def _raise_oserror(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "open", _raise_oserror)
    training_emitter.emit_training_record("command", {"query": "x"}, {"y": 1})
