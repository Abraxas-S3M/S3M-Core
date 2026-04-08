"""Tests for the Gymnasium-compatible wargame environment wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.simulation.gym_wargame_env import ACTION_HOLD, WargameEnv


def _write_minimal_scenario(path: Path, scenario_id: str | None = None) -> None:
    scenario_id_line = f'  scenario_id: "{scenario_id}"\n' if scenario_id else ""
    path.write_text(
        "scenario:\n"
        f"{scenario_id_line}"
        '  name: "RL Test Scenario"\n'
        '  type: "test"\n'
        '  description: "Minimal tactical test scenario"\n'
        "  terrain:\n"
        "    bounds: [[0, 0, 0], [100, 100, 50]]\n"
        "  weather:\n"
        "    visibility: 1.0\n"
        "    wind_speed: 0.0\n"
        "    wind_direction: 0.0\n"
        '    precipitation: "none"\n'
        "  forces:\n"
        '    - name: "Blue"\n'
        '      allegiance: "friendly"\n'
        "      units:\n"
        '        - {type: "FRIENDLY_UAV", count: 1, position: [5, 5, 5], behavior: "hold"}\n'
        '    - name: "Red"\n'
        '      allegiance: "enemy"\n'
        "      units:\n"
        '        - {type: "ENEMY_UGV", count: 1, position: [80, 80, 0], behavior: "hold"}\n'
        "  objectives:\n"
        '    - description: "No friendly losses"\n'
        '      success_condition: "friendly_losses == 0"\n'
        '  rules_of_engagement: "weapons_tight"\n'
        "  duration_seconds: 60\n",
        encoding="utf-8",
    )


def test_wargame_env_reset_and_step_records_episode_tuples(tmp_path) -> None:
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir(parents=True)
    _write_minimal_scenario(scenarios_dir / "rl_test.yaml", scenario_id="TEST-RL-01")

    env = WargameEnv(
        scenario_id="TEST-RL-01",
        scenarios_dir=str(scenarios_dir),
        max_units=4,
        max_threats=4,
        tick_dt=1.0,
        max_steps=4,
    )
    obs, info = env.reset()
    assert info["scenario_id"] == "TEST-RL-01"
    assert obs["unit_positions"].shape == (4, 3)
    assert obs["unit_health"].shape == (4,)
    assert obs["threat_positions"].shape == (4, 3)
    assert obs["threat_levels"].shape == (4,)

    action = np.full((4,), ACTION_HOLD, dtype=np.int64)
    _, reward, terminated, _, step_info = env.step(action)
    assert reward == pytest.approx(0.5)
    assert terminated is True
    assert step_info["objectives_met"] == ["No friendly losses"]

    episode = env.get_episode_tuples()
    assert len(episode) == 1
    assert set(episode[0].keys()) == {"observation", "action", "reward"}
    env.close()


def test_wargame_env_resolves_scenario_by_filename_stem(tmp_path) -> None:
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir(parents=True)
    _write_minimal_scenario(scenarios_dir / "stem_lookup.yaml")

    env = WargameEnv(
        scenario_id="stem_lookup",
        scenarios_dir=str(scenarios_dir),
        max_units=2,
        max_threats=2,
        tick_dt=1.0,
        max_steps=2,
    )
    _, info = env.reset()
    assert info["scenario_id"] == "stem_lookup"
    env.close()
