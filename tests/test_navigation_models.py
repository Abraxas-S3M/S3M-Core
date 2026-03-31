"""Unit tests for Layer 05 navigation domain models."""

from __future__ import annotations

from datetime import datetime, timezone

from src.navigation.models import (
    EdgeModel,
    GPSQuality,
    GPSStatus,
    JetsonStats,
    ModelPrecision,
    NavState,
    Path,
    PathStatus,
    PlannerType,
    PlatformConstraints,
    PlatformType,
    Pose,
    Trajectory,
    TrajectoryPoint,
    Waypoint,
)


def _pose() -> Pose:
    return Pose(
        position=(0.0, 0.0, 0.0),
        orientation=(0.0, 0.0, 1.0),
        velocity=(1.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.1),
        timestamp=datetime.now(timezone.utc),
        confidence=0.9,
        source="fused",
        covariance=[[1.0 if i == j else 0.0 for j in range(6)] for i in range(6)],
    )


def test_pose_creation_and_helpers():
    pose = _pose()
    payload = pose.to_dict()
    assert payload["source"] == "fused"
    other = Pose(
        position=(3.0, 4.0, 0.0),
        orientation=(0.0, 0.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        timestamp=datetime.now(timezone.utc),
        confidence=1.0,
        source="gps",
    )
    assert abs(pose.distance_to(other) - 5.0) < 1e-6
    assert 0.0 <= pose.heading_deg() <= 360.0


def test_gps_status_methods():
    good = GPSStatus(GPSQuality.GOOD, 8, 1.2, "3d", datetime.now(timezone.utc), (1.0, 2.0, 3.0))
    denied = GPSStatus(GPSQuality.DENIED, 0, 99.0, "none")
    assert good.is_usable() is True
    assert good.is_denied() is False
    assert denied.is_usable() is False
    assert denied.is_denied() is True


def test_nav_state_creation():
    nav = NavState(
        pose=_pose(),
        gps_status=GPSStatus(GPSQuality.GOOD, 8, 1.0, "3d"),
        localization_mode="gps_fused",
        active_sources=["gps", "imu"],
        drift_estimate_meters=1.2,
        last_update=datetime.now(timezone.utc),
    )
    out = nav.to_dict()
    assert out["localization_mode"] == "gps_fused"
    assert "pose" in out and "gps_status" in out


def test_waypoint_is_reached():
    wp = Waypoint(position=(10.0, 0.0, 0.0), radius=2.0)
    assert wp.is_reached((11.0, 0.0, 0.0)) is True
    assert wp.is_reached((13.1, 0.0, 0.0)) is False
    assert wp.is_reached((13.1, 0.0, 0.0), tolerance=4.0) is True


def test_path_trajectory_models():
    path = Path(
        path_id="p1",
        planner_type=PlannerType.RRT_STAR,
        status=PathStatus.PLANNED,
        waypoints=[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)],
        total_distance=10.0,
        estimated_time=2.0,
        obstacles_avoided=1,
        computation_time_ms=1.2,
        created_at=datetime.now(timezone.utc),
    )
    p0 = TrajectoryPoint(
        time=0.0,
        position=(0.0, 0.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        acceleration=(0.0, 0.0, 0.0),
        yaw=0.0,
        yaw_rate=0.0,
    )
    p1 = TrajectoryPoint(
        time=1.0,
        position=(10.0, 0.0, 0.0),
        velocity=(10.0, 0.0, 0.0),
        acceleration=(0.0, 0.0, 0.0),
        yaw=0.0,
        yaw_rate=0.0,
    )
    traj = Trajectory(
        trajectory_id="t1",
        path_id=path.path_id,
        points=[p0, p1],
        platform_type=PlatformType.QUADROTOR,
        duration=1.0,
        max_velocity=10.0,
        max_acceleration=0.0,
        feasible=True,
    )
    assert path.segment_count() == 1
    sample = traj.sample_at(0.5)
    assert abs(sample.position[0] - 5.0) < 1e-6


def test_platform_constraints_profiles():
    q = PlatformConstraints(
        platform_type=PlatformType.QUADROTOR,
        max_velocity=15.0,
        max_acceleration=5.0,
        max_jerk=20.0,
        max_yaw_rate=3.14,
        min_turn_radius=0.0,
        max_altitude=500.0,
        min_altitude=5.0,
        max_climb_rate=5.0,
        max_descent_rate=3.0,
        collision_radius=1.5,
    )
    u = PlatformConstraints(
        platform_type=PlatformType.GROUND_WHEELED,
        max_velocity=8.0,
        max_acceleration=2.0,
        max_jerk=10.0,
        max_yaw_rate=1.57,
        min_turn_radius=3.0,
        max_altitude=0.0,
        min_altitude=0.0,
        max_climb_rate=0.0,
        max_descent_rate=0.0,
        collision_radius=2.0,
    )
    f = PlatformConstraints(
        platform_type=PlatformType.FIXED_WING,
        max_velocity=40.0,
        max_acceleration=3.0,
        max_jerk=15.0,
        max_yaw_rate=0.52,
        min_turn_radius=50.0,
        max_altitude=3000.0,
        min_altitude=30.0,
        max_climb_rate=8.0,
        max_descent_rate=5.0,
        collision_radius=5.0,
    )
    assert q.max_velocity > u.max_velocity
    assert f.min_turn_radius > q.min_turn_radius


def test_edge_model_and_jetson_stats():
    model = EdgeModel(
        model_id="m1",
        name="demo.onnx",
        framework="onnx",
        precision=ModelPrecision.FP16,
        file_path="/tmp/demo.onnx",
        file_size_bytes=1000,
        input_shape=[1, 3, 224, 224],
        output_shape=[1, 1000],
        avg_latency_ms=2.0,
        memory_usage_mb=64.0,
        loaded=False,
    )
    assert model.to_dict()["precision"] == "fp16"
    stats = JetsonStats(
        gpu_utilization_pct=10.0,
        gpu_memory_used_mb=100.0,
        gpu_memory_total_mb=1000.0,
        cpu_utilization_pct=50.0,
        ram_used_mb=1000.0,
        ram_total_mb=2000.0,
        temperature_gpu_c=79.0,
        temperature_cpu_c=70.0,
        power_draw_watts=20.0,
        power_budget_watts=60.0,
        cuda_version=None,
        tensorrt_available=False,
        onnx_available=False,
    )
    assert stats.memory_pressure() >= 0.0
    assert stats.memory_pressure() <= 1.0
    assert stats.is_thermal_throttling() is False
    assert stats.is_thermal_throttling(threshold=75.0) is True
