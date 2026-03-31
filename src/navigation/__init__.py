"""
S3M Layer 05 — Navigation & Edge AI Inference
Provides GPS-denied localization, path planning, trajectory optimization,
and Jetson-optimized model inference for edge deployment.

Subsystems:
- Localization: Multi-source pose estimation (VIO, LiDAR-inertial, IMU dead reckoning)
- Planning: RRT*, A*, potential field path planning + min-snap trajectory optimization
- Edge Inference: TensorRT/ONNX model optimization + on-device LLM runtime

OODA Loop Integration:
  Sensor Fusion (Layer 02) → Localization (where am I?)
  Autonomy (Layer 03) → Planning (how do I get there?)
  Planning → Edge Inference (run models fast enough to react)
  Navigation → Autonomy (position updates close the loop)
"""

from src.navigation.edge_inference.edge_llm_runner import EdgeLLMRunner
from src.navigation.edge_inference.inference_engine import EdgeInferenceEngine
from src.navigation.edge_inference.jetson_monitor import JetsonMonitor
from src.navigation.edge_inference.model_optimizer import ModelOptimizer
from src.navigation.localization.localization_manager import LocalizationManager
from src.navigation.localization.pose_estimator import PoseEstimator
from src.navigation.models import (
    EdgeModel,
    GPSQuality,
    GPSStatus,
    InferenceResult,
    JetsonStats,
    ModelPrecision,
    NavState,
    Path,
    PathStatus,
    PlannerType,
    PlatformType,
    Pose,
    Trajectory,
    TrajectoryPoint,
    Waypoint,
)
from src.navigation.planning.collision_checker import CollisionChecker
from src.navigation.planning.path_planner import PathPlanner
from src.navigation.planning.trajectory_optimizer import TrajectoryOptimizer
from src.navigation.planning.waypoint_navigator import WaypointNavigator

__all__ = [
    "Pose",
    "NavState",
    "GPSStatus",
    "GPSQuality",
    "PlatformType",
    "Waypoint",
    "Path",
    "PathStatus",
    "Trajectory",
    "TrajectoryPoint",
    "PlannerType",
    "EdgeModel",
    "ModelPrecision",
    "InferenceResult",
    "JetsonStats",
    "LocalizationManager",
    "PoseEstimator",
    "PathPlanner",
    "TrajectoryOptimizer",
    "WaypointNavigator",
    "CollisionChecker",
    "ModelOptimizer",
    "EdgeInferenceEngine",
    "EdgeLLMRunner",
    "JetsonMonitor",
]
