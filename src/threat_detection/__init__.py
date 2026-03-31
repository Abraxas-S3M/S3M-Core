"""
S3M Layer 02 — Threat Detection
Provides network IDS integration (Suricata), endpoint SIEM (Wazuh),
object detection (YOLOv8), and anomaly detection pipelines.
Feeds structured threat alerts into Layer 01 (LLM Core) for analysis.

Components:
- ThreatManager: Central coordinator for all threat detection sources
- SuricataAdapter: Parses Suricata EVE JSON logs into S3M threat events
- WazuhAdapter: Parses Wazuh alerts into S3M threat events
- ObjectDetector: YOLOv8-based military target recognition (TensorRT-optimized)
- AnomalyDetector: ML-based anomaly detection on sensor/network telemetry
- ThreatEvent: Unified threat event data model
- ThreatClassifier: Routes threat events to appropriate LLM engine for assessment
"""

from src.threat_detection.anomaly_detector import AnomalyDetector
from src.threat_detection.models import (
    DetectionResult,
    ThreatCategory,
    ThreatEvent,
    ThreatLevel,
    ThreatSource,
)
from src.threat_detection.object_detector import ObjectDetector
from src.threat_detection.suricata_adapter import SuricataAdapter
from src.threat_detection.threat_classifier import ThreatClassifier
from src.threat_detection.threat_manager import ThreatManager
from src.threat_detection.wazuh_adapter import WazuhAdapter

__all__ = [
    "ThreatManager",
    "ThreatEvent",
    "ThreatLevel",
    "ThreatSource",
    "ThreatCategory",
    "SuricataAdapter",
    "WazuhAdapter",
    "ObjectDetector",
    "AnomalyDetector",
    "ThreatClassifier",
    "DetectionResult",
]
