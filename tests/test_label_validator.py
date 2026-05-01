from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.db.label_validator import LabelValidator


def _build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def test_validate_scenario_existing_updates_usage(tmp_path) -> None:
    config_path = tmp_path / "labels.yaml"
    config_path.write_text(
        """
tracks:
  general:
    default_labels: [intent, location]
    scenarios:
      convoy_brief: [intent, location, priority]
""".strip(),
        encoding="utf-8",
    )
    conn = _build_db()
    validator = LabelValidator(conn, config_path=config_path)
    validator.register_scenario("general", "convoy_brief", labels=["asset"])

    assert validator.validate_scenario("general", "convoy_brief") is True

    row = conn.execute(
        "SELECT use_count, labels FROM scenarios WHERE track = ? AND scenario = ?",
        ("general", "convoy_brief"),
    ).fetchone()
    assert row is not None
    assert int(row["use_count"]) == 2
    assert "asset" in str(row["labels"])


def test_validate_scenario_missing_auto_registers(tmp_path) -> None:
    config_path = tmp_path / "labels.yaml"
    config_path.write_text(
        """
tracks:
  operations:
    default_labels: [objective, location]
""".strip(),
        encoding="utf-8",
    )
    conn = _build_db()
    validator = LabelValidator(conn, config_path=config_path)

    assert validator.validate_scenario("operations", "mission_planning") is True

    row = conn.execute(
        "SELECT track, scenario, use_count FROM scenarios WHERE track = ? AND scenario = ?",
        ("operations", "mission_planning"),
    ).fetchone()
    assert row is not None
    assert row["track"] == "operations"
    assert row["scenario"] == "mission_planning"
    assert int(row["use_count"]) == 1


def test_register_scenario_merges_defaults_with_provided_labels(tmp_path) -> None:
    config_path = tmp_path / "labels.yaml"
    config_path.write_text(
        """
tracks:
  cop_intel:
    default_labels: [subject, indicator, confidence]
""".strip(),
        encoding="utf-8",
    )
    conn = _build_db()
    validator = LabelValidator(conn, config_path=config_path)

    record = validator.register_scenario(
        "cop_intel",
        "signal_intercept",
        labels=["origin", "confidence", "source"],
    )
    assert record["track"] == "cop_intel"
    assert record["scenario"] == "signal_intercept"
    assert record["labels"] == ["subject", "indicator", "confidence", "origin", "source"]


def test_get_labels_falls_back_to_defaults_when_db_record_missing(tmp_path) -> None:
    config_path = tmp_path / "labels.yaml"
    config_path.write_text(
        """
tracks:
  operations:
    default_labels: [objective, location]
    scenarios:
      cas_request: [asset, target_type, location, urgency]
""".strip(),
        encoding="utf-8",
    )
    conn = _build_db()
    validator = LabelValidator(conn, config_path=config_path)

    assert validator.get_labels("operations", "cas_request") == [
        "asset",
        "target_type",
        "location",
        "urgency",
    ]
    assert validator.get_labels("operations", "unknown_scenario") == ["objective", "location"]


def test_validate_example_reports_missing_labels(tmp_path) -> None:
    config_path = tmp_path / "labels.yaml"
    config_path.write_text(
        """
tracks:
  general:
    default_labels: [intent]
    scenarios:
      checkpoint_screening: [person, vehicle, risk_flag, location]
""".strip(),
        encoding="utf-8",
    )
    conn = _build_db()
    validator = LabelValidator(conn, config_path=config_path)

    is_valid, missing = validator.validate_example(
        {"person": "A", "location": "north gate"},
        "general",
        "checkpoint_screening",
    )
    assert is_valid is False
    assert missing == ["vehicle", "risk_flag"]


def test_get_all_scenarios_returns_track_scenario_label_mapping(tmp_path) -> None:
    config_path = tmp_path / "labels.yaml"
    config_path.write_text(
        """
tracks:
  general:
    default_labels: [intent, location]
    scenarios:
      convoy_brief: [intent, location, priority]
  operations:
    default_labels: [objective, location]
    scenarios:
      mission_planning: [objective, unit, location]
""".strip(),
        encoding="utf-8",
    )
    conn = _build_db()
    validator = LabelValidator(conn, config_path=config_path)
    validator.register_scenario("operations", "contingency_branch", labels=["trigger"])

    payload = validator.get_all_scenarios()
    assert payload["general"]["convoy_brief"] == ["intent", "location", "priority"]
    assert payload["operations"]["mission_planning"] == ["objective", "unit", "location"]
    assert payload["operations"]["contingency_branch"] == ["objective", "location", "trigger"]


def test_graceful_fallback_when_db_unavailable_uses_config_only(tmp_path) -> None:
    config_path = tmp_path / "labels.yaml"
    config_path.write_text(
        """
tracks:
  saudi_mod:
    default_labels: [intent, arabic_text]
    scenarios:
      bilingual_command_brief: [arabic_text, intent, priority]
""".strip(),
        encoding="utf-8",
    )
    conn = _build_db()
    validator = LabelValidator(conn, config_path=config_path)
    conn.close()

    assert validator.validate_scenario("saudi_mod", "bilingual_command_brief") is True
    assert validator.get_labels("saudi_mod", "bilingual_command_brief") == [
        "arabic_text",
        "intent",
        "priority",
    ]


def test_builtin_defaults_include_expected_track_and_scenario_counts() -> None:
    validator = LabelValidator(db_conn=None, config_path=Path("does-not-exist.yaml"))
    all_scenarios = validator.get_all_scenarios()
    assert set(all_scenarios) == {"general", "cop_intel", "saudi_mod", "operations"}
    assert len(all_scenarios["general"]) == 9
    assert len(all_scenarios["cop_intel"]) == 9
    assert len(all_scenarios["saudi_mod"]) == 10
    assert len(all_scenarios["operations"]) == 9
    assert sum(len(scenarios) for scenarios in all_scenarios.values()) == 37

