from services.comms.mesh_monitor import MeshNetworkMonitor
from services.comms.models import NodeType, RelayBackend
from services.comms.node_manager import CommsNodeManager


def test_get_mesh_status_filters_mesh_nodes_and_links() -> None:
    manager = CommsNodeManager()
    manager.register_node("MESH-A", NodeType.FIELD_UNIT, [RelayBackend.MESHTASTIC, RelayBackend.SIMULATED])
    manager.register_node("SIM-B", NodeType.FIELD_UNIT, [RelayBackend.SIMULATED])
    manager.register_node("MESH-C", NodeType.RELAY_NODE, [RelayBackend.MESHTASTIC])

    status = MeshNetworkMonitor(node_manager=manager).get_mesh_status()

    callsigns = {node["callsign"] for node in status["nodes"]}
    assert callsigns == {"MESH-A", "MESH-C"}
    assert all("meshtastic" in link["backends"] for link in status["links"])
    assert status["topology"] == "mesh"


def test_get_link_quality_prefers_reticulum_api() -> None:
    class FakeReticulum:
        @staticmethod
        def get_link_quality(node_a, node_b):
            assert node_a == "alpha"
            assert node_b == "bravo"
            return {"rssi": -88, "snr": 9.5, "latency": 74, "hops": 2}

    monitor = MeshNetworkMonitor(node_manager=CommsNodeManager(), reticulum_api=FakeReticulum())
    quality = monitor.get_link_quality("alpha", "bravo")

    assert quality == {"rssi": -88, "snr": 9.5, "latency": 74, "hops": 2}


def test_estimate_degradation_reports_weak_mesh_links() -> None:
    manager = CommsNodeManager()
    node_a = manager.register_node("LOW-A", NodeType.FIELD_UNIT, [RelayBackend.MESHTASTIC])
    node_b = manager.register_node("LOW-B", NodeType.FIELD_UNIT, [RelayBackend.MESHTASTIC])
    node_a.signal_strength = 0.1
    node_b.signal_strength = 0.15

    degradation = MeshNetworkMonitor(node_manager=manager).estimate_degradation()

    assert len(degradation["degraded_links"]) >= 1
    assert degradation["recommendations"]
