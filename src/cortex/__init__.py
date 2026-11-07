"""Cortex layer — policy gate, mission envelopes, engine council, and taint controls."""

from .envelope import CortexEnvelope, CortexEnvelopeCodec
from .policy_gate import (
    Approval,
    Approvals,
    MissionEnvelope,
    PolicyDecision,
    PolicyGate,
    PolicyGateConfig,
    PolicyVerdict,
    ToolCall,
)

__all__ = [
    "ACEResult",
    "Approval",
    "Approvals",
    "BrokerBypassError",
    "BrokerDenied",
    "CortexBroker",
    "CortexConfig",
    "CortexEnvelope",
    "CortexEnvelopeCodec",
    "CyberTaskType",
    "EngineCouncil",
    "MissionEnvelope",
    "PolicyDecision",
    "PolicyGate",
    "PolicyGateConfig",
    "PolicyVerdict",
    "ProductionDependencyError",
    "QuarantineExtractResult",
    "ReliabilityStore",
    "SameEngineFamilyError",
    "TaintSource",
    "TaintedPayload",
    "ToolCall",
    "assert_production_dependencies",
    "assert_tool_permitted",
    "cross_examine",
    "forbidden_tool_reason",
    "load_cortex_brain_config",
    "load_cortex_config",
    "quarantine_extract",
    "spotlight_datamark",
    "wrap_untrusted",
]


def __getattr__(name: str):
    """Lazy exports for cyber council and brain-upgrade modules."""
    if name in {"ACEResult", "ReliabilityStore", "SameEngineFamilyError", "cross_examine"}:
        from src.cortex import ace as _ace

        return getattr(_ace, name)
    if name in {"CyberTaskType", "EngineCouncil", "load_cortex_config"}:
        from src.cortex import council as _council

        return getattr(_council, name)
    if name in {
        "QuarantineExtractResult",
        "TaintSource",
        "TaintedPayload",
        "quarantine_extract",
        "spotlight_datamark",
        "wrap_untrusted",
    }:
        from src.cortex import taint as _taint

        return getattr(_taint, name)
    if name in {
        "BrokerBypassError",
        "BrokerDenied",
        "CortexBroker",
    }:
        from src.cortex import broker as _broker
        from src.cortex.changes import BrokerBypassError

        if name == "BrokerBypassError":
            return BrokerBypassError
        return getattr(_broker, name)
    if name in {
        "CortexConfig",
        "load_cortex_brain_config",
    }:
        from src.cortex import config as _config

        if name == "load_cortex_brain_config":
            return _config.load_cortex_config
        return getattr(_config, name)
    if name in {
        "ProductionDependencyError",
        "assert_production_dependencies",
    }:
        from src.cortex import runtime as _runtime

        return getattr(_runtime, name)
    if name in {"assert_tool_permitted", "forbidden_tool_reason"}:
        from src.cortex import tools as _tools

        return getattr(_tools, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
