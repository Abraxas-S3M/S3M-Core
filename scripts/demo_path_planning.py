#!/usr/bin/env python3
"""Path planning algorithm comparison demo for S3M Phase 8."""

from __future__ import annotations

import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.navigation.models import PlannerType
from src.navigation.planning.path_planner import PathPlanner
from src.navigation.planning.trajectory_optimizer import TrajectoryOptimizer


def make_obstacles(n: int = 10):
    random.seed(7)
    obs = []
    for idx in range(n):
        obs.append(
            {
                "id": f"obs-{idx}",
                "position": (
                    random.uniform(20.0, 180.0),
                    random.uniform(20.0, 180.0),
                    random.uniform(5.0, 25.0),
                ),
                "radius": random.uniform(5.0, 12.0),
            }
        )
    return obs


def main() -> None:
    planner = PathPlanner()
    optimizer = TrajectoryOptimizer()
    obstacles = make_obstacles()
    start = (5.0, 5.0, 10.0)
    goal = (195.0, 195.0, 10.0)
    bounds = ((0.0, 0.0, 0.0), (200.0, 200.0, 30.0))

    results = []
    for planner_type in [PlannerType.RRT_STAR, PlannerType.A_STAR, PlannerType.POTENTIAL_FIELD]:
        path = planner.plan(start, goal, obstacles=obstacles, planner_type=planner_type, bounds=bounds)
        traj = optimizer.optimize(path)
        feas = optimizer.check_feasibility(traj, optimizer.default_constraints)
        results.append(
            {
                "planner": planner_type.value,
                "distance": path.total_distance,
                "compute_ms": path.computation_time_ms,
                "waypoints": len(path.waypoints),
                "duration": traj.duration,
                "feasible": feas["feasible"],
            }
        )

    print("=== S3M Phase 8 Path Planning Comparison ===")
    print("Planner          Distance(m)  Compute(ms)  Waypoints  Duration(s)  Feasible")
    print("-" * 74)
    for row in results:
        print(
            f"{row['planner']:<16} {row['distance']:>11.1f} {row['compute_ms']:>11.2f}"
            f" {row['waypoints']:>10d} {row['duration']:>12.2f} {str(row['feasible']):>9}"
        )


if __name__ == "__main__":
    main()
