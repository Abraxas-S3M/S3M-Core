"""Unit tests for HOOL YAML configuration loader and bootstrap wiring."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from src.platforms.common import AuthorizationType, ROEProfile
from src.platforms.common.config_loader import bootstrap_hool_runtime, load_hool_configs


class _DummyAdapter:
    """Simple adapter used to validate config-driven platform registration."""

    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self._position = (0.0, 0.0, 0.0)
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def read_state(self) -> object:
        return types.SimpleNamespace(
            platform_id=self.platform_id,
            position=self._position,
            health_state=types.SimpleNamespace(value="nominal"),
        )


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _write_hool_config_pack(config_dir: Path) -> None:
    _write_yaml(
        config_dir / "platforms.yaml",
        """
        platforms:
          - platform_id: "alpha-1"
            type: "uav"
            adapter_class: "DummyAdapter"
            initial_position: [10.0, 20.0, 30.0]
        """,
    )
    _write_yaml(
        config_dir / "roe_profiles.yaml",
        """
        roe_profiles:
          default: "weapons_tight"
          zones:
            zone-red: "weapons_free"
            zone-safe: "weapons_hold"
        """,
    )
    _write_yaml(
        config_dir / "geofences.yaml",
        """
        geofences:
          - geofence_id: "allowed"
            policy: "allowed"
            polygon_xy:
              - [0.0, 0.0]
              - [100.0, 0.0]
              - [100.0, 100.0]
              - [0.0, 100.0]
          - geofence_id: "no-fire"
            policy: "forbidden"
            polygon_xy:
              - [40.0, 40.0]
              - [60.0, 40.0]
              - [60.0, 60.0]
              - [40.0, 60.0]
        """,
    )
    _write_yaml(
        config_dir / "missions.yaml",
        """
        missions:
          - mission_template_id: "demo"
            task_type: "patrol"
            assigned_platforms: ["alpha-1"]
            zone_id: "zone-red"
            waypoints:
              - [0.0, 0.0, 10.0]
              - [5.0, 5.0, 10.0]
        """,
    )
    _write_yaml(
        config_dir / "safety.yaml",
        """
        safety:
          health_poll_interval_seconds: 0.1
          operators:
            - operator_id: "op-1"
              authority_level: "operator"
            - operator_id: "cmd-1"
              authority_level: "mission_commander"
        """,
    )


def test_load_hool_configs_reads_required_files(tmp_path: Path) -> None:
    config_dir = tmp_path / "hool"
    config_dir.mkdir(parents=True)
    _write_hool_config_pack(config_dir)

    configs = load_hool_configs(config_dir=config_dir)
    assert "platforms" in configs.platforms
    assert "roe_profiles" in configs.roe_profiles
    assert "geofences" in configs.geofences
    assert "missions" in configs.missions
    assert "safety" in configs.safety


def test_bootstrap_hool_runtime_wires_all_services(tmp_path: Path) -> None:
    config_dir = tmp_path / "hool"
    config_dir.mkdir(parents=True)
    _write_hool_config_pack(config_dir)

    adapter_module = types.ModuleType("hool_test_adapters")
    adapter_module.DummyAdapter = _DummyAdapter
    sys.modules["hool_test_adapters"] = adapter_module

    runtime = bootstrap_hool_runtime(
        config_dir=config_dir,
        adapter_class_map={"DummyAdapter": "hool_test_adapters.DummyAdapter"},
    )

    platforms = runtime.platform_registry.list_platforms()
    assert len(platforms) == 1
    assert platforms[0].platform_id == "alpha-1"

    adapter = runtime.platform_registry.get_adapter("alpha-1")
    state = adapter.read_state()
    assert tuple(state.position) == (10.0, 20.0, 30.0)

    assert runtime.engagement_pipeline.resolve_roe_profile("zone-red") == ROEProfile.WEAPONS_FREE
    assert runtime.engagement_pipeline.resolve_roe_profile("zone-safe") == ROEProfile.WEAPONS_HOLD
    assert runtime.engagement_pipeline.resolve_roe_profile("unknown") == ROEProfile.WEAPONS_TIGHT

    # Tactical safety context: forbidden zone must always deny position checks.
    assert runtime.range_compliance_engine.check_position("alpha-1", (10.0, 10.0, 10.0))
    assert not runtime.range_compliance_engine.check_position("alpha-1", (50.0, 50.0, 10.0))

    assert set(runtime.registered_operators) == {"op-1", "cmd-1"}
    auth = runtime.control_authority_service.issue_authorization("cmd-1", AuthorizationType.ENGAGE)
    assert runtime.control_authority_service.validate_authorization(auth.auth_id)


def test_load_hool_configs_raises_when_required_file_missing(tmp_path: Path) -> None:
    config_dir = tmp_path / "hool"
    config_dir.mkdir(parents=True)
    _write_yaml(config_dir / "platforms.yaml", "platforms: []")
    with pytest.raises(FileNotFoundError):
        load_hool_configs(config_dir=config_dir)
