"""Unit tests for packet watcher ingestion and inference behavior."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
import yaml


def _load_packet_watcher_module(monkeypatch: pytest.MonkeyPatch):
    # Inject src.training.packet_builder under the import path expected by watcher.
    from src.training.packet_builder import PacketBuilder as SrcPacketBuilder

    training_mod = types.ModuleType("training")
    packet_builder_mod = types.ModuleType("training.packet_builder")
    packet_builder_mod.PacketBuilder = SrcPacketBuilder
    training_mod.packet_builder = packet_builder_mod
    monkeypatch.setitem(sys.modules, "training", training_mod)
    monkeypatch.setitem(sys.modules, "training.packet_builder", packet_builder_mod)

    module_name = "packet_watcher_under_test"
    module_path = Path("src/pipeline/packet_watcher.py")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to import packet_watcher module for tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_track_config(path: Path) -> None:
    payload = {
        "tracks": {
            "cop_intel": {
                "default_data_class": "cop_intel",
                "scenarios": {
                    "threat_assessment": {"data_class": "cop_intel"},
                },
            },
            "saudi_mod": {
                "default_data_class": "command",
                "scenarios": {
                    "border_security": {"data_class": "command"},
                },
            },
            "general": {
                "default_data_class": "command",
                "scenarios": ["command"],
            },
            "operations": {
                "default_data_class": "command",
                "scenarios": ["convoy_planning"],
            },
        }
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _build_watcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_packet_watcher_module(monkeypatch)
    inbox = tmp_path / "inbox"
    staging = tmp_path / "staging"
    output_root = tmp_path / "tracks"
    config = tmp_path / "tracks.yaml"
    log_path = tmp_path / "packet_watcher.log"
    _write_track_config(config)

    monkeypatch.setattr(module, "LOG_FILE", log_path)
    watcher = module.PacketWatcher(
        inbox_dir=inbox,
        staging_dir=staging,
        packet_output_root=output_root,
        tracks_config_path=config,
        poll_interval_seconds=1,
    )
    return module, watcher, inbox, staging, output_root


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def test_infers_track_and_scenario_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, watcher, _, _, _ = _build_watcher(tmp_path, monkeypatch)

    cases = {
        "cop_intel_threat_assessment_001.jsonl": ("cop_intel", "threat_assessment"),
        "saudi_mod_border_security_v2.jsonl": ("saudi_mod", "border_security"),
        "general_command_batch3.jsonl": ("general", "command"),
        "operations_convoy_planning.jsonl": ("operations", "convoy_planning"),
    }
    for filename, expected in cases.items():
        inferred = watcher._infer_track_scenario(filename)
        assert (inferred.track, inferred.scenario) == expected


def test_process_file_moves_successful_jsonl_to_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module, watcher, inbox, staging, output_root = _build_watcher(tmp_path, monkeypatch)
    packet_name = "operations_convoy_planning.jsonl"
    source = inbox / packet_name
    _write_jsonl(
        source,
        [{"prompt": "Plan convoy route", "completion": "Use route bravo with ISR cover"}],
    )

    watcher._process_file(source)

    assert not source.exists()
    assert (staging / packet_name).exists()
    created_dirs = sorted((output_root / "operations" / "scenarios").glob("scenario-*"))
    assert created_dirs, "Packet builder should create at least one scenario directory"
    assert module.LOG_FILE.exists()


def test_unknown_scenario_is_auto_registered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, watcher, _, _, _ = _build_watcher(tmp_path, monkeypatch)
    assert "new_scenario" not in watcher._track_definitions["operations"].scenarios

    watcher._validate_or_register_scenario(
        track="operations",
        scenario="new_scenario",
        data_class="command",
        filename="operations_new_scenario.jsonl",
    )

    assert "new_scenario" in watcher._track_definitions["operations"].scenarios


def test_malformed_json_raises_and_does_not_move_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, watcher, inbox, staging, _ = _build_watcher(tmp_path, monkeypatch)
    packet_name = "general_command_batch3.jsonl"
    source = inbox / packet_name
    source.write_text('{"prompt": "ok", "completion": "ok"}\n{"prompt": "bad"\n', encoding="utf-8")

    with pytest.raises(ValueError):
        watcher._process_file(source)

    assert source.exists()
    assert not (staging / packet_name).exists()


def test_known_scenario_allowed_when_validator_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, watcher, _, _, _ = _build_watcher(tmp_path, monkeypatch)
    watcher._label_validator = None

    watcher._validate_or_register_scenario(
        track="operations",
        scenario="convoy_planning",
        data_class="command",
        filename="operations_convoy_planning.jsonl",
    )
