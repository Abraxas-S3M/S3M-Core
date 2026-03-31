# PHASE 8 — Navigation & Edge AI Inference (Layer 05)

## Overview

Phase 8 delivers the physical execution layer for S3M. It converts autonomy intent into
real movement and low-latency edge inference on NVIDIA Jetson AGX Orin 64GB.

Military/tactical context:
- In contested environments, GPS denial, thermal limits, and collision risk can degrade mission success.
- Layer 05 provides resilient localization, route planning, trajectory feasibility checks, and on-device AI execution.
- All logic runs offline with graceful degradation when optional packages are unavailable.

## Architecture and Data Flow

```
Layer 02 Sensor Fusion / Threat Detection
    └─ fused tracks, obstacle objects, telemetry
            ↓
Layer 05 Navigation
    ├─ LocalizationManager
    │    ├─ GPSMonitor
    │    ├─ VINSAdapter (optional ROS2)
    │    ├─ LidarOdomAdapter (optional ROS2)
    │    ├─ PoseEstimator (EKF fusion)
    │    └─ DeadReckoning fallback
    │
    ├─ PlanningManager
    │    ├─ PathPlanner (RRT*, A*, Potential Field)
    │    ├─ CollisionChecker (static + moving tracks)
    │    ├─ TrajectoryOptimizer (minimum-snap style + fallback)
    │    └─ WaypointNavigator (mission sequencing / replan)
    │
    └─ Edge Inference
         ├─ ModelOptimizer (PyTorch → ONNX → TensorRT when available)
         ├─ EdgeInferenceEngine (TensorRT > ONNX Runtime > PyTorch > stub)
         ├─ EdgeLLMRunner (TensorRT engine or llama.cpp .gguf)
         └─ JetsonMonitor (thermal, memory, power telemetry)
            ↓
Layer 03 Autonomy
    └─ receives updated pose, route state, collision status, and performance signals
```

## Localization Subsystem

### Multi-source fusion
- `PoseEstimator` reuses `src.sensor_fusion.ekf_filter.EKFFilter` with state vector:
  `[x, y, z, vx, vy, vz]`.
- Sensor updates:
  - GPS position updates
  - VIO pose updates
  - LiDAR odometry updates
  - IMU prediction updates
- Runtime source weights allow trust tuning for degraded conditions.

### GPS denial and spoofing detection
- `GPSMonitor` classifies quality:
  - EXCELLENT: low HDOP, high satellites
  - GOOD: moderate HDOP, sufficient satellites
  - DEGRADED: marginal HDOP/satellite count
  - DENIED: no fix / too few satellites
  - SPOOFED: large position jump over threshold
- Quality transition history supports post-mission analysis.

### Dead reckoning fallback
- `DeadReckoning` integrates IMU acceleration and angular velocity when external aids are unavailable.
- Confidence decays over time (`0.001/update`) to reflect drift accumulation.
- External correction reanchors the state when GPS/VIO/LiDAR return.

### Adapter pattern
- `VINSAdapter` and `LidarOdomAdapter` use ROS2 subscription only if `rclpy` is available.
- Both provide offline `load_from_file()` parsing for CSV/TUM-style trajectories.
- No blocking ROS spin loops; polling is non-blocking (`spin_once`).

## Path Planning Subsystem

### RRT*
Use case:
- 3D navigation with sparse/irregular obstacles where global optimality and obstacle avoidance matter.

Features:
- Sampling-based tree growth in 3D
- Parent rewiring for cost improvement
- Goal connection checks
- Post-solution path smoothing

### A*
Use case:
- 2D ground route planning over quasi-flat terrain.

Features:
- Grid discretization
- 8-connected neighborhood
- Euclidean heuristic
- Obstacle occupancy blocking

### Potential Field
Use case:
- Fast reactive planning in simpler scenes.

Features:
- Attractive goal force + repulsive obstacle force
- Local-minima detection and fallback to RRT* when progress stalls

### Straight-line fallback
- Baseline route when no obstacles or when planner fallback is required.

## Trajectory Optimization

### Minimum-snap style polynomial trajectory
- Time allocation by segment distance and platform velocity limit.
- Per-axis seventh-order polynomial coefficients satisfy continuity-like boundary constraints.
- Trajectory sampled at fixed `dt` into `TrajectoryPoint` stream.

### Feasibility enforcement
- Checks velocity, acceleration, jerk, and altitude limits against `PlatformConstraints`.
- If violations exist, planner retimes (increases segment time) and retries.

### MPC path
- `optimize_with_mpc()` attempts acados integration when available.
- Falls back to polynomial optimizer if acados is missing.

## Waypoint Navigation

- `WaypointNavigator` executes waypoint missions segment-by-segment.
- Supports:
  - waypoint radius checks
  - loiter handling
  - mission progress reporting
  - abort/replan controls
- Designed for behavior-tree integration (Patrol / RTB style loops).

## Collision Checking

### Path and trajectory safety
- Segment-level line-sphere intersection against static obstacles.
- Time-aware checks against moving tracks (forward-predicted with velocity).
- Reports:
  - collision list
  - nearest miss distance
  - time-to-collision estimate

### Safe corridor generation
- `find_safe_corridor()` computes broad corridor waypoints for formation/swam movement.
- Supports wider clearance than single-vehicle centerline paths.

## Edge Inference

### Model optimization pipeline
1. Detect input format (`.pt/.pth`, `.onnx`, `.engine/.trt`)
2. Convert PyTorch to ONNX when possible
3. Convert ONNX to TensorRT when available
4. Benchmark and return metadata as `EdgeModel`

All stages use try/except fallback to prevent mission software crashes.

### Inference backend priority
`TensorRT > ONNX Runtime > PyTorch > stub`

- `EdgeInferenceEngine` tracks loaded models, latency, and memory usage.
- Stub mode returns structured warning output when no runtime exists.

## Edge LLM for communications-denied operations

- `EdgeLLMRunner` supports:
  - TensorRT engine loading for `.engine/.trt` when available
  - llama.cpp runtime for `.gguf` models
  - stub mode fallback when unavailable
- Memory gate prevents loading models over configured budget.

## Jetson Monitoring

- `JetsonMonitor` samples:
  - GPU utilization
  - system and GPU memory estimates
  - thermal zones
  - power draw
  - CUDA / TensorRT / ONNX runtime presence
- When not on Jetson hardware, simulated stats are returned with explicit marker.

### Thermal and memory load shedding
- `is_thermal_throttling()` checks threshold crossing.
- `recommend_model_budget()` reserves headroom before loading new models.

## Platform Constraints Profiles

- `configs/platforms/uav_quadrotor.yaml`
- `configs/platforms/ugv_wheeled.yaml`
- `configs/platforms/fixed_wing.yaml`

These define mission-critical dynamic constraints:
- max velocity/acceleration/jerk
- yaw-rate and turn radius
- altitude envelope
- climb/descent rates
- collision radius

## API Reference (20 endpoints)

### Localization
1. `GET /navigation/status`
2. `GET /navigation/pose`
3. `GET /navigation/pose/history?limit=50`
4. `GET /navigation/gps/status`
5. `POST /navigation/localization/reset`

Example reset body:
```json
{"position": [0.0, 0.0, 10.0]}
```

### Planning
6. `POST /navigation/plan`
7. `POST /navigation/plan/waypoints`
8. `GET /navigation/plan/{plan_id}`
9. `POST /navigation/plan/{plan_id}/replan`
10. `GET /navigation/plan/{plan_id}/collision-check`
11. `POST /navigation/plan/{plan_id}/update`
12. `POST /navigation/trajectory/optimize`

Example plan request:
```json
{
  "start": [0, 0, 10],
  "goal": [120, 80, 20],
  "obstacles": [{"position": [60, 40, 15], "radius": 20}],
  "planner_type": "rrt_star",
  "platform_type": "quadrotor"
}
```

### Edge Inference
13. `GET /navigation/edge/status`
14. `GET /navigation/edge/models`
15. `POST /navigation/edge/models/optimize`
16. `POST /navigation/edge/predict`
17. `GET /navigation/edge/llm/status`

### Jetson
18. `GET /navigation/jetson/health`
19. `GET /navigation/jetson/memory`
20. `GET /navigation/jetson/capabilities`

## Configuration Reference

Primary file: `configs/navigation.yaml`

Main sections:
- `localization`
- `planning`
- `edge_inference`
- `jetson`
- `platforms_dir`

Key operational parameters:
- GPS denial thresholds
- planner defaults and tuning
- trajectory sampling and retiming controls
- edge model memory limits
- thermal throttle thresholds

## Integration with Phases 1–7 (OODA closure)

- Layer 03 autonomy commands enter Layer 05 planner/navigator.
- Layer 02 fused tracks and threat objects become obstacle/track inputs.
- Layer 05 pose updates and route state return to autonomy decision loops.
- Edge inference acceleration supports Layer 01/Layer 02 model workloads on Jetson.

This closes sensing → orientation/localization → decision/planning → action/feedback.

## Testing Instructions

Run navigation-related tests:

```bash
python -m pytest \
  tests/test_navigation_*.py \
  tests/test_pose_*.py \
  tests/test_dead_*.py \
  tests/test_gps_*.py \
  tests/test_localization_*.py \
  tests/test_path_*.py \
  tests/test_trajectory_*.py \
  tests/test_waypoint_*.py \
  tests/test_collision_*.py \
  tests/test_model_*.py \
  tests/test_edge_*.py \
  tests/test_jetson_*.py -v
```

No external packages are required for base test pass; optional integrations degrade gracefully.

## Future Work

- **Phase 9**: dashboard integration for live route/thermal overlays and mission replay.
- **Phase 10**: security hardening (model artifact signing, stricter route policy gates, runtime attestation).
