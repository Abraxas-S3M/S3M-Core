"""Tests for PoseEstimator EKF-based localization fusion."""

from src.navigation.localization.pose_estimator import PoseEstimator


def test_initialization_creates_ekf():
    estimator = PoseEstimator(dt=0.05)
    assert estimator.ekf is not None
    assert estimator.get_source_weights()["gps"] == 1.0


def test_update_from_gps_moves_estimate_toward_position():
    estimator = PoseEstimator()
    estimator.reset((0.0, 0.0, 0.0))
    estimator.update_from_gps((10.0, 0.0, 0.0))
    pose = estimator.get_pose()
    assert pose.position[0] > 0.1


def test_update_from_imu_propagates_state_prediction():
    estimator = PoseEstimator()
    estimator.reset((0.0, 0.0, 0.0))
    estimator.update_from_imu((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.1)
    pose = estimator.get_pose()
    assert pose.position[0] >= 0.0


def test_fusing_gps_plus_imu_better_than_imu_only():
    imu_only = PoseEstimator()
    imu_only.reset((0.0, 0.0, 0.0))
    for _ in range(20):
        imu_only.update_from_imu((0.5, 0.0, 0.0), (0.0, 0.0, 0.0), 0.1)
    imu_pose = imu_only.get_pose()

    fused = PoseEstimator()
    fused.reset((0.0, 0.0, 0.0))
    for _ in range(20):
        fused.update_from_imu((0.5, 0.0, 0.0), (0.0, 0.0, 0.0), 0.1)
        fused.update_from_gps((1.0, 0.0, 0.0))
    fused_pose = fused.get_pose()

    imu_error = abs(imu_pose.position[0] - 1.0)
    fused_error = abs(fused_pose.position[0] - 1.0)
    assert fused_error <= imu_error


def test_drift_estimate_increases_with_imu_only_updates():
    estimator = PoseEstimator()
    estimator.reset((0.0, 0.0, 0.0))
    base = estimator.get_drift_estimate()
    for _ in range(50):
        estimator.update_from_imu((0.2, 0.0, 0.0), (0.0, 0.0, 0.0), 0.1)
        estimator.get_pose()
    drift = estimator.get_drift_estimate()
    assert drift >= base


def test_reset_clears_state():
    estimator = PoseEstimator()
    estimator.update_from_gps((5.0, 0.0, 0.0))
    estimator.reset((0.0, 0.0, 0.0))
    pose = estimator.get_pose()
    assert abs(pose.position[0]) < 0.5
