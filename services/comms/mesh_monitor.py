"""Mesh-network telemetry monitor for tactical Layer 08 operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.comms.models import RelayBackend
from services.comms.node_manager import CommsNodeManager

try:
    import RNS
except Exception:  # pragma: no cover - optional dependency in test/runtime variants
    RNS = None  # type: ignore[assignment]


class MeshNetworkMonitor:
    """Observe mesh topology and estimate tactical comms degradation risk."""

    def __init__(
        self,
        node_manager: Optional[CommsNodeManager] = None,
        reticulum_api: Any = None,
    ) -> None:
        self.node_manager = node_manager or CommsNodeManager()
        self._reticulum_api = reticulum_api if reticulum_api is not None else RNS

    def get_mesh_status(self) -> Dict[str, Any]:
        topology = self.node_manager.get_network_topology()
        mesh_nodes = [
            node
            for node in topology.get("nodes", [])
            if RelayBackend.MESHTASTIC.value in node.get("relay_backends", [])
        ]
        mesh_links = [
            link
            for link in topology.get("links", [])
            if RelayBackend.MESHTASTIC.value in link.get("backends", [])
        ]
        return {"nodes": mesh_nodes, "links": mesh_links, "topology": "mesh"}

    def get_link_quality(self, node_a: str, node_b: str) -> Dict[str, Any]:
        node_a_id = self._normalize_node_id(node_a)
        node_b_id = self._normalize_node_id(node_b)
        if not node_a_id or not node_b_id:
            return {"rssi": None, "snr": None, "latency": None, "hops": None}

        observed = self._read_reticulum_quality(node_a_id, node_b_id)
        if observed:
            return observed

        source = self.node_manager.get_node(node_a_id)
        target = self.node_manager.get_node(node_b_id)
        if source is None or target is None:
            return {"rssi": None, "snr": None, "latency": None, "hops": None}

        if RelayBackend.MESHTASTIC not in source.relay_backends or RelayBackend.MESHTASTIC not in target.relay_backends:
            return {"rssi": None, "snr": None, "latency": None, "hops": None}

        score = max(0.0, min(1.0, (source.signal_strength + target.signal_strength) / 2.0))
        hops = 1 if score >= 0.7 else 2 if score >= 0.45 else 3
        return {
            "rssi": int(round(-120.0 + (score * 80.0))),
            "snr": round(-5.0 + (score * 25.0), 1),
            "latency": int(round(40.0 + ((1.0 - score) * 420.0))),
            "hops": hops,
        }

    def estimate_degradation(self) -> Dict[str, Any]:
        status = self.get_mesh_status()
        degraded_links: List[Dict[str, Any]] = []
        for link in status.get("links", []):
            source = str(link.get("from", "")).strip()
            target = str(link.get("to", "")).strip()
            if not source or not target:
                continue
            quality = self.get_link_quality(source, target)
            if self._is_degraded_link(quality):
                degraded_links.append({"from": source, "to": target, **quality})

        recommendations: List[str] = []
        if degraded_links:
            recommendations.append(
                "Prioritize command-and-control traffic over the strongest mesh links until link quality stabilizes."
            )
            if any(link.get("latency", 0) and link["latency"] > 300 for link in degraded_links):
                recommendations.append(
                    "Queue non-critical telemetry to protect tactical command traffic during high-latency mesh windows."
                )
            if any(link.get("hops", 0) and link["hops"] >= 3 for link in degraded_links):
                recommendations.append(
                    "Deploy an additional relay node to reduce hop count and improve mesh resilience for maneuver units."
                )
        else:
            recommendations.append(
                "Maintain current mesh routing and continue heartbeat checks to preserve command-network continuity."
            )

        return {"degraded_links": degraded_links, "recommendations": recommendations}

    def _normalize_node_id(self, node_ref: str) -> Optional[str]:
        value = str(node_ref).strip()
        if not value:
            return None
        node = self.node_manager.get_node(value)
        if node is not None:
            return node.node_id
        node = self.node_manager.get_node_by_callsign(value)
        if node is not None:
            return node.node_id
        return value

    @staticmethod
    def _is_degraded_link(quality: Dict[str, Any]) -> bool:
        rssi = quality.get("rssi")
        snr = quality.get("snr")
        latency = quality.get("latency")
        hops = quality.get("hops")
        return bool(
            (isinstance(rssi, (int, float)) and rssi < -95)
            or (isinstance(snr, (int, float)) and snr < 2)
            or (isinstance(latency, (int, float)) and latency > 300)
            or (isinstance(hops, int) and hops > 2)
        )

    def _read_reticulum_quality(self, node_a: str, node_b: str) -> Optional[Dict[str, Any]]:
        api = self._reticulum_api
        if api is None:
            return None

        for method_name in ("get_link_quality", "link_quality", "get_link_stats"):
            method = getattr(api, method_name, None)
            if not callable(method):
                continue
            try:
                payload = method(node_a, node_b)
            except Exception:
                continue
            normalized = self._normalize_quality_payload(payload)
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def _normalize_quality_payload(payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        if not {"rssi", "snr", "latency", "hops"}.issubset(payload.keys()):
            return None
        return {
            "rssi": payload.get("rssi"),
            "snr": payload.get("snr"),
            "latency": payload.get("latency"),
            "hops": payload.get("hops"),
        }
