"""Behavioral threat detection stack for S3M defensive operations."""

from .anomaly_detector import AnomalyScore, BehavioralAnomalyDetector, SessionLog
from .attack_patterns import (
    AttackPattern,
    AttackPatternLibrary,
    DetectionRule,
    PatternMatch,
    SecurityEvent,
)
from .sequence_analyzer import CommandSequenceAnalyzer, SequenceAlert
from .threat_correlator import (
    Evidence,
    FileChangeEvent,
    ProcAccessAlert,
    ThreatAssessment,
    ThreatCorrelator,
    TrafficEntry,
)

__all__ = [
    "AnomalyScore",
    "AttackPattern",
    "AttackPatternLibrary",
    "BehavioralAnomalyDetector",
    "CommandSequenceAnalyzer",
    "DetectionRule",
    "Evidence",
    "FileChangeEvent",
    "PatternMatch",
    "ProcAccessAlert",
    "SecurityEvent",
    "SequenceAlert",
    "SessionLog",
    "ThreatAssessment",
    "ThreatCorrelator",
    "TrafficEntry",
]

