#!/usr/bin/env python3
"""S3M Phase 8 full navigation pipeline demo.

Military context:
This dry-run demonstrates how Layer 05 maintains mission mobility when GPS is
contested and still drives safe route execution and edge compute awareness.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.navigation.localization.localization_manager import LocalizationManager
from src.navigation.models import PlannerType, Pose, Waypoint
from src.navigation.planning.collision_checker import CollisionChecker
from src.navigation.planning.path_planner import PathPlanner
from src.navigation.planning.trajectory_optimizer import TrajectoryOptimizer
from src.navigation.planning.waypoint_navigator import WaypointNavigator
from src.navigation.edge_inference.jetson_monitor import JetsonMonitor


def run_demo() -> None:
    print("=" * 72)
    print("S3M PHASE 8 DEMO — NAVIGATION & EDGE AI")
    print("=" * 72)

    loc = LocalizationManager()
    loc.start()
    print("\n[1] Simulate nominal GPS + IMU updates")
    for i in range(5):
        state = loc.update(
            imu_data={"linear_accel": (0.1, 0.0, 0.0), "angular_vel": (0.0, 0.0, 0.01), "dt": 0.1},
            gps_data={"satellites": 10, "hdop": 1.2, "fix_type": "3d", "position": (i * 1.2, 0.0, 10.0)},
        )
        print(f"  step={i} mode={state.localization_mode} pos={state.pose.position} conf={state.pose.confidence:.3f}")

    print("\n[2] Simulate GPS denial and fallback")
    loc.gps_monitor.simulate_denial()
    for i in range(4):
        state = loc.update(
            imu_data={"linear_accel": (0.05, 0.02, 0.0), "angular_vel": (0.0, 0.0, 0.015), "dt": 0.1},
            gps_data={"satellites": 1, "hdop": 50.0, "fix_type": "none", "position": None},
        )
        print(f"  denied step={i} mode={state.localization_mode} pos={state.pose.position}")

    print("\n[3] Restore GPS and observe correction")
    loc.gps_monitor.simulate_restore()
    restored = loc.update(
        imu_data={"linear_accel": (0.0, 0.0, 0.0), "angular_vel": (0.0, 0.0, 0.0), "dt": 0.1},
        gps_data={"satellites": 9, "hdop": 2.0, "fix_type": "3d", "position": (15.0, 2.0, 10.0)},
    )
    print(f"  restored mode={restored.localization_mode} pos={restored.pose.position}")

    print("\n[4] Plan RRT* path around 5 obstacles")
    planner = PathPlanner(default_planner=PlannerType.RRT_STAR)
    start = (0.0, 0.0, 10.0)
    goal = (120.0, 120.0, 20.0)
    obstacles = [
        {"id": f"obs-{i}", "position": (random.uniform(20, 100), random.uniform(20, 100), 15.0), "radius": 10.0}
        for i in range(5)
    ]
    path = planner.plan(start=start, goal=goal, obstacles=obstacles, planner_type=PlannerType.RRT_STAR)
    print(f"  path_id={path.path_id} waypoints={len(path.waypoints)} dist={path.total_distance:.1f}m")

    print("\n[5] Optimize trajectory for quadrotor")
    optimizer = TrajectoryOptimizer()
    traj = optimizer.optimize(path)
    print(f"  trajectory_id={traj.trajectory_id} duration={traj.duration:.1f}s feasible={traj.feasible}")

    print("\n[6] Execute waypoint mission")
    nav = WaypointNavigator(path_planner=planner, trajectory_optimizer=optimizer)
    mission_id = nav.load_mission(
        [
            Waypoint(position=(0.0, 0.0, 10.0), radius=2.0),
            Waypoint(position=(30.0, 20.0, 12.0), radius=2.0),
            Waypoint(position=(70.0, 60.0, 15.0), radius=2.0, loiter_seconds=0.2),
            Waypoint(position=(120.0, 120.0, 20.0), radius=3.0),
        ]
    )
    nav.start()
    print(f"  mission={mission_id}")
    pose = Pose(
        position=(0.0, 0.0, 10.0),
        orientation=(0.0, 0.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        timestamp=restored.pose.timestamp,
        confidence=1.0,
        source="demo",
    )
    for _ in range(10):
        update = nav.update(pose)
        target = update["target_position"]
        pose = Pose(
            position=target,
            orientation=(0.0, 0.0, float(update["target_yaw"])),
            velocity=update["target_velocity"],
            angular_velocity=(0.0, 0.0, 0.0),
            timestamp=restored.pose.timestamp,
            confidence=1.0,
            source="demo",
        )
        print(f"  status={update['status']} wp={update['waypoint_index']} progress={update['segment_progress']:.2f}")
        if update["status"] == "completed":
            break
        time.sleep(0.02)

    print("\n[7] Collision check against simulated moving tracks")
    checker = CollisionChecker()
    tracks = [{"track_id": "trk-1", "position": (40.0, 40.0, 12.0), "velocity": (0.2, -0.1, 0.0), "radius": 4.0}]
    collision = checker.check_trajectory(traj, obstacles=obstacles, other_tracks=tracks)
    pprint(collision)

    print("\n[8] Jetson monitor stats (simulated on non-Jetson)")
    jm = JetsonMonitor()
    stats = jm.get_stats()
    pprint(stats.to_dict())
    print("  simulated:", jm.is_simulated())

    print("\n[9] Subsystem health summary")
    pprint(
        {
            "localization": loc.health_check(),
            "navigator": nav.get_status(),
            "jetson": {"thermal_throttling": jm.is_thermal_throttling(), "budget_mb": jm.recommend_model_budget()},
        }
    )
    print("\nDemo complete.")


if __name__ == "__main__":
    run_demo()
