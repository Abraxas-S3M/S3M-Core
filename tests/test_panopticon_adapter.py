"""Tests for Panopticon adapter graceful behavior when server unavailable."""

from src.simulation.adapters.panopticon_adapter import PanopticonAdapter
from src.simulation.models import SimConfig


def test_panopticon_adapter_initializes():
    adapter = PanopticonAdapter(SimConfig(simulator_name="panopticon"))
    assert adapter is not None


def test_panopticon_connect_false_without_server():
    adapter = PanopticonAdapter(SimConfig(simulator_name="panopticon", host="localhost", port=59999))
    assert adapter.connect() is False


def test_panopticon_health_unavailable():
    adapter = PanopticonAdapter(SimConfig(simulator_name="panopticon", host="localhost", port=59999))
    health = adapter.health_check()
    assert health["available"] is False
