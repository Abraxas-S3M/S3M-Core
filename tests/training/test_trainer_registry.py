"""Unit tests for TrainerRegistry route configuration resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.training.trainer_registry import TrainerRegistry


def test_default_track_assignments_are_applied() -> None:
    registry = TrainerRegistry(config_path=Path("/tmp/does-not-exist.yaml"))

    general = registry.get_trainer_config("general", "any_scenario")
    assert general["trainer_type"] == "causal_lm"
    assert general["learning_rate"] == 2e-5
    assert general["batch_size"] == 8

    cop_intel = registry.get_trainer_config("cop_intel", "intel_push")
    assert cop_intel["trainer_type"] == "causal_lm"
    assert cop_intel["learning_rate"] == 1e-5
    assert cop_intel["batch_size"] == 4

    saudi_mod = registry.get_trainer_config("saudi_mod", "air_defense")
    assert saudi_mod["trainer_type"] == "causal_lm"
    assert saudi_mod["learning_rate"] == 2e-5
    assert saudi_mod["batch_size"] == 4

    operations = registry.get_trainer_config("operations", "mission_planning")
    assert operations["trainer_type"] == "causal_lm"
    assert operations["learning_rate"] == 2e-5
    assert operations["batch_size"] == 8


def test_register_trainer_supports_specific_scenario_override() -> None:
    registry = TrainerRegistry(config_path=Path("/tmp/does-not-exist.yaml"))
    registry.register_trainer(
        "general",
        "urban_patrol",
        {
            "trainer_type": "classification",
            "base_model": "models/quantized/urban-classifier",
            "learning_rate": 3e-5,
            "batch_size": 16,
            "max_epochs": 8,
            "warmup_steps": 50,
            "gradient_accumulation": 1,
            "mixed_precision": True,
            "runpod_template": "runpod-urban-classifier",
        },
    )

    specific = registry.get_trainer_config("general", "urban_patrol")
    wildcard = registry.get_trainer_config("general", "different_scenario")

    assert specific["trainer_type"] == "classification"
    assert specific["batch_size"] == 16
    assert wildcard["trainer_type"] == "causal_lm"
    assert wildcard["batch_size"] == 8


def test_list_trainers_contains_route_metadata() -> None:
    registry = TrainerRegistry(config_path=Path("/tmp/does-not-exist.yaml"))
    entries = registry.list_trainers()

    assert entries
    assert any(item["track"] == "general" and item["scenario"] == "*" for item in entries)
    assert all("runpod_template" in item for item in entries)


def test_get_trainer_config_raises_for_unknown_track() -> None:
    registry = TrainerRegistry(config_path=Path("/tmp/does-not-exist.yaml"))
    with pytest.raises(KeyError):
        registry.get_trainer_config("unknown_track", "scenario_alpha")


def test_register_trainer_rejects_invalid_payload() -> None:
    registry = TrainerRegistry(config_path=Path("/tmp/does-not-exist.yaml"))
    with pytest.raises(ValueError):
        registry.register_trainer(
            "general",
            "scenario",
            {
                "trainer_type": "causal_lm",
                "base_model": "models/quantized/placeholder",
                "learning_rate": -0.1,
                "batch_size": 8,
                "max_epochs": 2,
                "warmup_steps": 0,
                "gradient_accumulation": 1,
                "mixed_precision": True,
                "runpod_template": "runpod-template",
            },
        )
