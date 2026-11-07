"""Partition-scoped network twin for Cortex quarantine decisions."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, Iterable, List, Optional, Set, Tuple

from src.cortex.models import MissionBinding, MissionFlow, NetworkEdge


class NetworkTwin:
    """In-memory connectivity twin with mission-required flows and protected edges."""

    def __init__(self) -> None:
        self._edges: Dict[str, NetworkEdge] = {}
        self._bindings: Dict[str, MissionBinding] = {}
        self.required_flows: Set[Tuple[str, str, str]] = set()
        self.protected_edges: Set[str] = set()
        self._partition_edges: Dict[str, Set[str]] = defaultdict(set)

    def add_edge(self, edge: NetworkEdge) -> None:
        if not isinstance(edge, NetworkEdge):
            raise TypeError("edge must be a NetworkEdge")
        self._edges[edge.edge_id] = edge
        self._partition_edges[edge.partition].add(edge.edge_id)

    def edges_for_partition(self, partition: str) -> List[NetworkEdge]:
        return [self._edges[eid] for eid in self._partition_edges.get(partition, set())]

    def incident_edges(self, node: str) -> List[NetworkEdge]:
        node = str(node)
        return [
            e
            for e in self._edges.values()
            if e.source == node or e.destination == node
        ]

    def store_binding(self, binding: MissionBinding) -> None:
        self._bindings[binding.mission_id] = binding

    def get_binding(self, mission_id: str) -> Optional[MissionBinding]:
        return self._bindings.get(mission_id)

    def active_bindings(self) -> List[MissionBinding]:
        return [b for b in self._bindings.values() if b.active]

    def activate_binding(self, mission_id: str) -> MissionBinding:
        binding = self._require_binding(mission_id)
        updated = binding.model_copy(update={"active": True})
        self._bindings[mission_id] = updated
        self._rebuild_mission_state()
        return updated

    def deactivate_binding(self, mission_id: str) -> MissionBinding:
        binding = self._require_binding(mission_id)
        updated = binding.model_copy(update={"active": False})
        self._bindings[mission_id] = updated
        self._rebuild_mission_state()
        return updated

    def _require_binding(self, mission_id: str) -> MissionBinding:
        binding = self._bindings.get(mission_id)
        if binding is None:
            raise KeyError(f"unknown mission_id: {mission_id}")
        return binding

    def _rebuild_mission_state(self) -> None:
        self.required_flows.clear()
        self.protected_edges.clear()
        for binding in self.active_bindings():
            for flow in binding.flows:
                key = (flow.source, flow.destination, flow.purpose)
                self.required_flows.add(key)
                for edge in self._edges_on_any_path(flow.source, flow.destination):
                    self.protected_edges.add(edge.edge_id)

    def _edges_on_any_path(self, source: str, destination: str) -> List[NetworkEdge]:
        """Return edges belonging to one shortest path (BFS), if reachable."""
        path_nodes = self._shortest_path_nodes(source, destination)
        if not path_nodes:
            return []
        edges: List[NetworkEdge] = []
        for left, right in zip(path_nodes, path_nodes[1:]):
            edge = self._find_directed_edge(left, right)
            if edge:
                edges.append(edge)
        return edges

    def _find_directed_edge(self, source: str, destination: str) -> Optional[NetworkEdge]:
        for edge in self._edges.values():
            if edge.source == source and edge.destination == destination:
                return edge
        return None

    def _shortest_path_nodes(self, source: str, destination: str) -> List[str]:
        if source == destination:
            return [source]
        adj: Dict[str, List[str]] = defaultdict(list)
        for edge in self._edges.values():
            adj[edge.source].append(edge.destination)
        queue: deque[str] = deque([source])
        parent: Dict[str, Optional[str]] = {source: None}
        while queue:
            node = queue.popleft()
            for nxt in adj.get(node, []):
                if nxt in parent:
                    continue
                parent[nxt] = node
                if nxt == destination:
                    return self._reconstruct(parent, destination)
                queue.append(nxt)
        return []

    @staticmethod
    def _reconstruct(parent: Dict[str, Optional[str]], destination: str) -> List[str]:
        path: List[str] = []
        cursor: Optional[str] = destination
        while cursor is not None:
            path.append(cursor)
            cursor = parent.get(cursor)
        path.reverse()
        return path

    def shortest_path_through(
        self, source: str, destination: str, via: str
    ) -> List[NetworkEdge]:
        """Shortest edge sequence from source to destination that visits ``via``."""
        if via == source:
            prefix: List[str] = [source]
        else:
            prefix = self._shortest_path_nodes(source, via)
            if not prefix or prefix[-1] != via:
                return []
        if via == destination:
            suffix = []
        else:
            suffix = self._shortest_path_nodes(via, destination)
            if not suffix or suffix[0] != via:
                return []
            suffix = suffix[1:]
        nodes = prefix + suffix
        edges: List[NetworkEdge] = []
        for left, right in zip(nodes, nodes[1:]):
            edge = self._find_directed_edge(left, right)
            if edge is None:
                return []
            edges.append(edge)
        return edges

    def active_flows_through_node(self, node: str) -> List[MissionFlow]:
        node = str(node)
        flows: List[MissionFlow] = []
        for binding in self.active_bindings():
            for flow in binding.flows:
                path = self.shortest_path_through(flow.source, flow.destination, node)
                if path:
                    flows.append(flow)
        return flows

    def partition_mission_flows_at_node(self, node: str) -> List[MissionFlow]:
        """Active binding flows scoped to the suspect node's partition (quarantine set)."""
        node = str(node)
        incident = self.incident_edges(node)
        if not incident:
            return []
        partition = incident[0].partition
        flows: List[MissionFlow] = []
        for binding in self.active_bindings():
            if binding.partition != partition:
                continue
            flows.extend(binding.flows)
        return flows

    def edge_supports_active_mission(self, edge_id: str) -> bool:
        return edge_id in self.protected_edges

    def highest_active_priority_on_edge(self, edge_id: str) -> int:
        """Return the max mission priority among active bindings using this edge."""
        edge = self._edges.get(edge_id)
        if edge is None:
            return 0
        best = 0
        for binding in self.active_bindings():
            for flow in binding.flows:
                for path_edge in self._edges_on_any_path(flow.source, flow.destination):
                    if path_edge.edge_id == edge_id:
                        best = max(best, binding.priority)
        return best

    def candidate_disruption_edges(self, node: str) -> List[NetworkEdge]:
        return self.incident_edges(node)
