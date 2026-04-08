import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

_services_pkg = ModuleType("services")
_services_pkg.__path__ = []  # type: ignore[attr-defined]
_comms_pkg = ModuleType("services.comms")
_comms_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules["services"] = _services_pkg
sys.modules["services.comms"] = _comms_pkg

_ROOT = Path(__file__).resolve().parents[1]

_models_path = _ROOT / "services" / "comms" / "models.py"
_models_spec = spec_from_file_location("services.comms.models", _models_path)
assert _models_spec and _models_spec.loader
_models_module = module_from_spec(_models_spec)
sys.modules["services.comms.models"] = _models_module
_models_spec.loader.exec_module(_models_module)

_node_manager_path = _ROOT / "services" / "comms" / "node_manager.py"
_node_spec = spec_from_file_location("services.comms.node_manager", _node_manager_path)
assert _node_spec and _node_spec.loader
_node_module = module_from_spec(_node_spec)
sys.modules["services.comms.node_manager"] = _node_module
_node_spec.loader.exec_module(_node_module)

_mesh_monitor_path = _ROOT / "services" / "comms" / "mesh_monitor.py"
_mesh_spec = spec_from_file_location("mesh_monitor_under_test", _mesh_monitor_path)
assert _mesh_spec and _mesh_spec.loader
_mesh_module = module_from_spec(_mesh_spec)
sys.modules["mesh_monitor_under_test"] = _mesh_module
_mesh_spec.loader.exec_module(_mesh_module)

MeshNetworkMonitor = _mesh_module.MeshNetworkMonitor
NodeType = _models_module.NodeType
RelayBackend = _models_module.RelayBackend
CommsNodeManager = _node_module.CommsNodeManager


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
