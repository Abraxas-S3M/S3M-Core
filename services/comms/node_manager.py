"""Comms node registry and topology manager for Layer 08."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from services.comms.models import CommsNode, NodeType, RelayBackend


class CommsNodeManager:
    """Track comms-capable nodes and network liveness in tactical operations."""

    def __init__(self) -> None:
        self.nodes: Dict[str, CommsNode] = {}

    def register_node(
        self,
        callsign: str,
        node_type: NodeType | str,
        relay_backends: List[RelayBackend | str],
        position: Optional[Tuple[float, float, float]] = None,
    ) -> CommsNode:
        normalized_type = node_type if isinstance(node_type, NodeType) else NodeType(str(node_type))
        normalized_backends: List[RelayBackend] = []
        for backend in relay_backends:
            if isinstance(backend, RelayBackend):
                normalized_backends.append(backend)
            else:
                normalized_backends.append(RelayBackend(str(backend).lower()))
        node = CommsNode(
            node_id=f"node-{uuid4().hex[:10]}",
            callsign=callsign,
            node_type=normalized_type,
            relay_backends=normalized_backends,
            position=position,
            last_heartbeat=datetime.now(timezone.utc),
            status="online",
            signal_strength=1.0,
            battery_pct=100.0,
        )
        self.nodes[node.node_id] = node
        return node

    def remove_node(self, node_id: str) -> bool:
        return self.nodes.pop(node_id, None) is not None

    def update_node(self, node_id: str, **kwargs) -> Optional[CommsNode]:
        node = self.nodes.get(node_id)
        if not node:
            return None
        for key, value in kwargs.items():
            if hasattr(node, key):
                setattr(node, key, value)
        return node

    def heartbeat(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        if node is None:
            return False
        node.last_heartbeat = datetime.now(timezone.utc)
        node.status = "online"
        return True

    def get_node(self, node_id: str) -> Optional[CommsNode]:
        return self.nodes.get(node_id)

    def get_node_by_callsign(self, callsign: str) -> Optional[CommsNode]:
        match = callsign.strip().lower()
        for node in self.nodes.values():
            if node.callsign.strip().lower() == match:
                return node
        return None

    def get_nodes(self, node_type: Optional[NodeType] = None, status: Optional[str] = None) -> List[CommsNode]:
        entries = list(self.nodes.values())
        if node_type is not None:
            entries = [node for node in entries if node.node_type == node_type]
        if status is not None:
            normalized = status.strip().lower()
            entries = [node for node in entries if node.status.lower() == normalized]
        return entries

    def get_network_topology(self) -> dict:
        nodes = [node.to_dict() for node in self.nodes.values()]
        links: List[dict] = []
        for source in self.nodes.values():
            for target in self.nodes.values():
                if source.node_id == target.node_id:
                    continue
                shared = set(source.relay_backends).intersection(set(target.relay_backends))
                if shared:
                    links.append(
                        {
                            "from": source.node_id,
                            "to": target.node_id,
                            "backends": [backend.value for backend in sorted(shared, key=lambda b: b.value)],
                        }
                    )
        return {
            "nodes": nodes,
            "links": links,
            "counts": {
                "mesh_nodes": len([n for n in self.nodes.values() if RelayBackend.MESHTASTIC in n.relay_backends]),
                "command_nodes": len([n for n in self.nodes.values() if n.node_type == NodeType.COMMAND_CENTER]),
                "field_nodes": len([n for n in self.nodes.values() if n.node_type == NodeType.FIELD_UNIT]),
            },
        }

    def detect_lost_nodes(self, timeout_seconds: int = 300) -> List[CommsNode]:
        lost: List[CommsNode] = []
        for node in self.nodes.values():
            if node.time_since_heartbeat() > float(timeout_seconds):
                node.status = "lost"
                lost.append(node)
        return lost

    def get_stats(self) -> dict:
        total = len(self.nodes)
        online = len([node for node in self.nodes.values() if node.is_online()])
        lost = len([node for node in self.nodes.values() if node.status.lower() == "lost"])
        return {
            "total_nodes": total,
            "online_nodes": online,
            "lost_nodes": lost,
            "by_type": {
                node_type.value: len([node for node in self.nodes.values() if node.node_type == node_type])
                for node_type in NodeType
            },
        }

