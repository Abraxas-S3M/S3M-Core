"""Network containment primitives for S3M defensive controls."""

from .dns_guard import DNSGuard, DNSQuery
from .egress_proxy import EgressProxy, ExfilAlert, TrafficEntry
from .policy_engine import NetworkPolicy, NetworkPolicyEngine, NetworkRequest, PolicyDecision
from .traffic_analyzer import ThreatAssessment, ThreatIndicator, TrafficAnalyzer

__all__ = [
    "DNSGuard",
    "DNSQuery",
    "EgressProxy",
    "ExfilAlert",
    "NetworkPolicy",
    "NetworkPolicyEngine",
    "NetworkRequest",
    "PolicyDecision",
    "ThreatAssessment",
    "ThreatIndicator",
    "TrafficAnalyzer",
    "TrafficEntry",
]
