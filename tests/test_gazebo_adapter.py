from src.simulation.adapters import GazeboAdapter
from src.simulation.models import SimConfig


def test_gazebo_adapter_graceful_without_rclpy():
    adapter = GazeboAdapter(SimConfig(simulator_name="gazebo"))
    assert adapter.connect() is False


def test_gazebo_connect_false_without_rclpy():
    adapter = GazeboAdapter(SimConfig(simulator_name="gazebo"))
    assert adapter.connect() is False


def test_gazebo_health_check_unavailable():
    adapter = GazeboAdapter(SimConfig(simulator_name="gazebo"))
    health = adapter.health_check()
    assert health["adapter"] == "gazebo"
    assert health["available"] is False
