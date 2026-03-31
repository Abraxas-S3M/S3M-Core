#!/usr/bin/env python3
"""Tests for NLCommander keyword fallback behavior."""

from src.autonomy.models import CommandType
from src.autonomy.swarm import NLCommander


def test_move_to_grid_keyword_fallback():
    commander = NLCommander()
    cmd = commander.parse_command("move to grid 100 200 50")
    assert cmd.command_type == CommandType.MOVE_TO
    assert cmd.parameters.get("waypoint") == [100.0, 200.0, 50.0]


def test_hold_position_keyword_fallback():
    commander = NLCommander()
    cmd = commander.parse_command("hold position")
    assert cmd.command_type == CommandType.HOLD


def test_emergency_stop_keyword_fallback():
    commander = NLCommander()
    cmd = commander.parse_command("emergency stop now")
    assert cmd.command_type == CommandType.EMERGENCY_STOP


def test_arabic_rtb_keyword():
    commander = NLCommander()
    cmd = commander.parse_arabic_command("عودة للقاعدة")
    assert cmd.command_type == CommandType.RTB


def test_invalid_input_default():
    commander = NLCommander()
    cmd = commander.parse_command("nonsense input with no tactical command")
    assert cmd.command_type == CommandType.HOLD
