"""
S3M Sensor Fusion Foundation
Multi-modal sensor data processing and fusion for tactical awareness.
Supports EKF/UKF state estimation, multi-sensor track fusion,
and feeds fused tracks into the Threat Detection layer.
"""

from src.sensor_fusion.ekf_filter import EKFFilter
from src.sensor_fusion.models import SensorReading, SensorType, Track, TrackState
from src.sensor_fusion.multi_hypothesis_tracker import MultiHypothesisTracker
from src.sensor_fusion.sensor_manager import SensorManager
from src.sensor_fusion.sidc_generator import generate_sidc
from src.sensor_fusion.track_fuser import TrackFuser

__all__ = [
    "SensorType",
    "SensorReading",
    "Track",
    "TrackState",
    "EKFFilter",
    "TrackFuser",
    "MultiHypothesisTracker",
    "StoneSoupBridge",
    "SensorManager",
    "generate_sidc",
]
