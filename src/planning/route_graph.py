"""Threat-aware tactical route graph built on top of networkx."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import networkx as nx

GridCoord = tuple[int, int]


@dataclass(frozen=True)
class _ThreatZone:
    x: float
    y: float
    radius: float
    intensity: float


class TacticalRouteGraph:
    """Builds tactical movement routes with threat-influenced edge costs."""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._grid_size: GridCoord = (0, 0)
        self._threats: list[_ThreatZone] = []

    def build_from_terrain(self, grid_size: Sequence[int], obstacles: Iterable[object]) -> "TacticalRouteGraph":
        """Create a 2D movement graph while excluding blocked terrain cells."""
        width, height = self._normalize_grid_size(grid_size)
        blocked_cells = self._normalize_obstacles(obstacles, width=width, height=height)

        self.graph = nx.DiGraph()
        self._grid_size = (width, height)

        for y in range(height):
            for x in range(width):
                node = (x, y)
                if node in blocked_cells:
                    continue
                self.graph.add_node(node)

        # Tactical context: permit 8-direction movement to model realistic
        # maneuver options for alternate approaches around hazards.
        directions = (
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
            (-1, -1),
            (-1, 1),
            (1, -1),
            (1, 1),
        )
        nodes = list(self.graph.nodes)
        for x, y in nodes:
            for dx, dy in directions:
                neighbor = (x + dx, y + dy)
                if neighbor not in self.graph:
                    continue
                base_distance = math.hypot(dx, dy)
                threat_penalty = self._edge_threat_penalty((x, y), neighbor)
                self.graph.add_edge(
                    (x, y),
                    neighbor,
                    base_distance=base_distance,
                    threat_penalty=threat_penalty,
                    weight=base_distance + threat_penalty,
                )
        return self

    def add_threat_overlay(self, threats: Iterable[object]) -> None:
        """Apply threat-derived weight penalties to nearby movement edges."""
        self._threats = self._normalize_threats(threats)
        for source, target, attributes in self.graph.edges(data=True):
            base_distance = float(attributes.get("base_distance", self._distance(source, target)))
            threat_penalty = self._edge_threat_penalty(source, target)
            attributes["base_distance"] = base_distance
            attributes["threat_penalty"] = threat_penalty
            attributes["weight"] = base_distance + threat_penalty

    def find_route(self, start: object, end: object, algorithm: str = "astar") -> list[GridCoord]:
        """Return the primary route between start and end using weighted pathfinding."""
        start_node = self._normalize_point(start, label="start")
        end_node = self._normalize_point(end, label="end")
        if start_node not in self.graph or end_node not in self.graph:
            return []

        try:
            if algorithm == "astar":
                return nx.astar_path(
                    self.graph,
                    start_node,
                    end_node,
                    heuristic=self._astar_heuristic,
                    weight="weight",
                )
            if algorithm == "dijkstra":
                return nx.shortest_path(self.graph, start_node, end_node, weight="weight", method="dijkstra")
            raise ValueError("algorithm must be either 'astar' or 'dijkstra'")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def find_alternate_routes(self, start: object, end: object, k: int = 3) -> list[list[GridCoord]]:
        """Return up to k tactical route alternatives ordered by weighted cost."""
        if not isinstance(k, int) or k <= 0:
            raise ValueError("k must be a positive integer")

        start_node = self._normalize_point(start, label="start")
        end_node = self._normalize_point(end, label="end")
        if start_node not in self.graph or end_node not in self.graph:
            return []

        try:
            path_iterator = nx.shortest_simple_paths(self.graph, start_node, end_node, weight="weight")
            routes: list[list[GridCoord]] = []
            for _ in range(k):
                try:
                    routes.append(next(path_iterator))
                except StopIteration:
                    break
            return routes
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    @staticmethod
    def _normalize_grid_size(grid_size: Sequence[int]) -> GridCoord:
        if not isinstance(grid_size, Sequence) or len(grid_size) != 2:
            raise ValueError("grid_size must be a sequence of two integers")
        width = TacticalRouteGraph._coerce_int(grid_size[0], label="grid width")
        height = TacticalRouteGraph._coerce_int(grid_size[1], label="grid height")
        if width <= 0 or height <= 0:
            raise ValueError("grid dimensions must be positive")
        return width, height

    @staticmethod
    def _coerce_int(value: object, *, label: str) -> int:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be numeric") from exc
        if not math.isfinite(number):
            raise ValueError(f"{label} must be finite")
        return int(round(number))

    @classmethod
    def _normalize_point(cls, point: object, *, label: str) -> GridCoord:
        if isinstance(point, dict):
            if "x" in point and "y" in point:
                return cls._coerce_int(point["x"], label=f"{label}.x"), cls._coerce_int(point["y"], label=f"{label}.y")
            if "position" in point:
                return cls._normalize_point(point["position"], label=label)
            raise ValueError(f"{label} must provide x/y coordinates")
        if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) >= 2:
            return cls._coerce_int(point[0], label=f"{label}.x"), cls._coerce_int(point[1], label=f"{label}.y")
        raise ValueError(f"{label} must be a coordinate pair")

    @classmethod
    def _normalize_obstacles(cls, obstacles: Iterable[object], *, width: int, height: int) -> set[GridCoord]:
        blocked: set[GridCoord] = set()
        if obstacles is None:
            return blocked
        for obstacle in obstacles:
            try:
                x, y = cls._normalize_point(obstacle, label="obstacle")
            except ValueError:
                continue
            if 0 <= x < width and 0 <= y < height:
                blocked.add((x, y))
        return blocked

    @classmethod
    def _normalize_threats(cls, threats: Iterable[object]) -> list[_ThreatZone]:
        normalized: list[_ThreatZone] = []
        if threats is None:
            return normalized
        for threat in threats:
            if not isinstance(threat, dict):
                continue
            try:
                x, y = cls._normalize_point(threat, label="threat")
            except ValueError:
                continue
            radius = threat.get("radius", threat.get("influence_radius", 2.0))
            intensity = threat.get("penalty", threat.get("threat_penalty", threat.get("severity", 4.0)))
            try:
                radius_value = float(radius)
                intensity_value = float(intensity)
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(radius_value) and math.isfinite(intensity_value)):
                continue
            if radius_value <= 0.0 or intensity_value <= 0.0:
                continue
            normalized.append(_ThreatZone(x=float(x), y=float(y), radius=radius_value, intensity=intensity_value))
        return normalized

    def _edge_threat_penalty(self, source: GridCoord, target: GridCoord) -> float:
        if not self._threats:
            return 0.0
        midpoint_x = (source[0] + target[0]) / 2.0
        midpoint_y = (source[1] + target[1]) / 2.0

        total_penalty = 0.0
        for threat in self._threats:
            distance = math.hypot(midpoint_x - threat.x, midpoint_y - threat.y)
            if distance > threat.radius:
                continue
            # Tactical context: routes that pass close to known hostile zones
            # incur higher costs to bias maneuver away from likely enemy fires.
            proximity = (threat.radius - distance) / threat.radius
            total_penalty += threat.intensity * (1.0 + proximity)
        return total_penalty

    @staticmethod
    def _distance(source: GridCoord, target: GridCoord) -> float:
        return math.hypot(target[0] - source[0], target[1] - source[1])

    @staticmethod
    def _astar_heuristic(current: GridCoord, goal: GridCoord) -> float:
        return math.hypot(goal[0] - current[0], goal[1] - current[1])
