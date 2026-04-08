"""Unit tests for threat-aware tactical route graph planning."""

from __future__ import annotations

import pytest

from src.planning.route_graph import TacticalRouteGraph


def test_build_from_terrain_excludes_obstacles_and_finds_route() -> None:
    graph = TacticalRouteGraph().build_from_terrain(grid_size=(5, 5), obstacles=[(2, 2)])
    route = graph.find_route(start=(0, 0), end=(4, 4))

    assert route[0] == (0, 0)
    assert route[-1] == (4, 4)
    assert (2, 2) not in route


def test_add_threat_overlay_increases_edge_weight_near_threat() -> None:
    graph = TacticalRouteGraph().build_from_terrain(grid_size=(3, 3), obstacles=[])
    baseline_weight = graph.graph[(0, 0)][(1, 0)]["weight"]

    graph.add_threat_overlay([{"x": 1, "y": 0, "radius": 2.0, "severity": 5.0}])
    threat_weight = graph.graph[(0, 0)][(1, 0)]["weight"]

    assert threat_weight > baseline_weight


def test_find_alternate_routes_returns_up_to_k_routes() -> None:
    graph = TacticalRouteGraph().build_from_terrain(grid_size=(4, 4), obstacles=[])
    routes = graph.find_alternate_routes(start=(0, 0), end=(3, 3), k=3)

    assert len(routes) == 3
    assert all(route[0] == (0, 0) for route in routes)
    assert all(route[-1] == (3, 3) for route in routes)


def test_find_alternate_routes_rejects_invalid_k() -> None:
    graph = TacticalRouteGraph().build_from_terrain(grid_size=(4, 4), obstacles=[])

    with pytest.raises(ValueError, match="positive integer"):
        graph.find_alternate_routes(start=(0, 0), end=(3, 3), k=0)
