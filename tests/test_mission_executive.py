#!/usr/bin/env python3
"""Unit tests for mission executive autonomy extension."""

from __future__ import annotations

from src.autonomy.mission_executive import (
    ExecutiveMissionType,
    MissionExecutive,
    MissionPhase,
    MobilityCommand,
    SensorCommand,
)


def _assert_only_nav_sensor_commands(commands: list[object]) -> None:
    assert commands
    assert all(isinstance(cmd, (MobilityCommand, SensorCommand)) for cmd in commands)


def test_phase_flow_idle_deploy_transit_on_station() -> None:
    executive = MissionExecutive()
    executive.start_mission(
        mission_type=ExecutiveMissionType.PATROL,
        mission_context={
            "station_position": [100.0, 0.0, 0.0],
            "current_position": [0.0, 0.0, 0.0],
            "waypoints": [[100.0, 0.0, 0.0], [120.0, 0.0, 0.0]],
        },
    )
    assert executive.phase == MissionPhase.DEPLOY

    deploy_cmds = executive.update()
    _assert_only_nav_sensor_commands(deploy_cmds)
    assert executive.phase == MissionPhase.TRANSIT

    arrive_cmds = executive.update({"current_position": [100.0, 0.0, 0.0]})
    _assert_only_nav_sensor_commands(arrive_cmds)
    assert executive.phase == MissionPhase.ON_STATION


def test_safety_comms_loss_forces_rtb() -> None:
    executive = MissionExecutive(fuel_critical_pct=20.0)
    executive.start_mission(
        mission_type="isr",
        mission_context={
            "station_position": [250.0, 0.0, 0.0],
            "base_position": [0.0, 0.0, 0.0],
            "current_position": [10.0, 0.0, 0.0],
            "comms_status": "nominal",
            "fuel_pct": 75.0,
        },
    )
    executive.update()  # deploy -> transit
    commands = executive.update({"comms_status": "lost"})
    _assert_only_nav_sensor_commands(commands)
    assert executive.phase == MissionPhase.RTB
    assert executive.context.get("rtb_reason") == "comms_lost"


def test_all_supported_mission_types_emit_only_mobility_and_sensor_commands() -> None:
    for mission_type in ExecutiveMissionType:
        executive = MissionExecutive()
        executive.start_mission(
            mission_type=mission_type,
            mission_context={
                "station_position": [50.0, 0.0, 0.0],
                "current_position": [0.0, 0.0, 0.0],
                "base_position": [0.0, 0.0, 0.0],
                "waypoints": [[50.0, 0.0, 0.0], [75.0, 0.0, 0.0]],
                "intercept_target_position": [55.0, 0.0, 0.0],
            },
        )
        executive.update()  # deploy -> transit
        executive.update({"current_position": [50.0, 0.0, 0.0]})  # transit -> on_station
        cmds = executive.update()  # mission-specific tick
        _assert_only_nav_sensor_commands(cmds)


def test_pause_resume_abort_lifecycle() -> None:
    executive = MissionExecutive()
    executive.start_mission("station_keep", {"station_position": [10.0, 0.0, 0.0], "current_position": [0.0, 0.0, 0.0]})
    executive.update()  # deploy -> transit
    executive.pause()
    assert executive.phase == MissionPhase.PAUSED
    executive.resume()
    assert executive.phase == MissionPhase.TRANSIT
    executive.abort()
    assert executive.phase == MissionPhase.ABORTED
    assert executive.update() == []
