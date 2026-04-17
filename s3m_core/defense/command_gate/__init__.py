"""Command analysis and gate layer for S3M defense."""

from .command_parser import CommandAST, CommandParser, Redirect
from .execution_gate import ExecutionGate, ExecutionPolicy, ExecutionResult, GateDecision
from .obfuscation_detector import ObfuscationDetector, ObfuscationReport
from .threat_classifier import CommandThreatClassifier, CommandThreatScore, ThreatDetail

__all__ = [
    "CommandAST",
    "CommandParser",
    "CommandThreatClassifier",
    "CommandThreatScore",
    "ExecutionGate",
    "ExecutionPolicy",
    "ExecutionResult",
    "GateDecision",
    "ObfuscationDetector",
    "ObfuscationReport",
    "Redirect",
    "ThreatDetail",
]
