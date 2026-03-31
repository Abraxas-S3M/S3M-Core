"""Tests for JSBSim adapter graceful fallback behavior."""

from src.simulation.adapters.jsbsim_adapter import JSBSimAdapter
from src.simulation.models import SimConfig


def test_jsbsim_adapter_initializes_without_package():
    adapter = JSBSimAdapter(SimConfig(simulator_name="jsbsim"))
    health = adapter.health_check()
    assert health["adapter"] == "jsbsim"
    assert health["available"] is False


def test_jsbsim_connect_false_without_package():
    adapter = JSBSimAdapter(SimConfig(simulator_name="jsbsim"))
    assert adapter.connect() is False


def test_jsbsim_health_reports_unavailable():
    adapter = JSBSimAdapter(SimConfig(simulator_name="jsbsim"))
    adapter.connect()
    health = adapter.health_check()
    assert health["available"] is False
    assert health["connected"] is False
