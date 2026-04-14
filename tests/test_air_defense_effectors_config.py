"""Unit tests for air defense effector type configuration."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_air_defense_effectors_config_has_expected_schema() -> None:
    config_path = Path("configs/air_defense/effectors.yaml")
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    effector_types = config_data.get("effector_types")
    assert isinstance(effector_types, dict)
    assert len(effector_types) == 6

    for effector_key, effector in effector_types.items():
        assert isinstance(effector_key, str) and effector_key
        assert isinstance(effector.get("name_en"), str) and effector["name_en"]
        assert isinstance(effector.get("name_ar"), str) and effector["name_ar"]
        assert isinstance(effector.get("category"), str) and effector["category"]
        assert isinstance(effector.get("echelon"), str) and effector["echelon"]
        assert isinstance(effector.get("typical_ammo"), int) and effector["typical_ammo"] >= 0
        assert isinstance(effector.get("reload_time_s"), int) and effector["reload_time_s"] >= 0

        envelope = effector.get("envelope")
        assert isinstance(envelope, dict)
        assert envelope["min_range_m"] >= 0
        assert envelope["max_range_m"] > envelope["min_range_m"]
        assert envelope["min_altitude_m"] >= 0
        assert envelope["max_altitude_m"] >= envelope["min_altitude_m"]
        assert envelope["max_target_speed_mps"] > 0
        assert envelope["reaction_time_s"] >= 0
        assert envelope["engagement_time_s"] >= 0
        assert envelope["simultaneous_targets"] >= 1
        # Tactical context: probability of kill must remain a bounded confidence input.
        assert 0.0 <= envelope["pk_single_shot"] <= 1.0
