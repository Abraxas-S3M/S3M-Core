"""Cortex layer — policy gate, mission envelopes, engine council, and admission."""

from src.cortex.change_control_gate import (
    ChangeClass,
    ChangeControlGate,
    ChangeEnvelope,
    SignedDeviceApproval,
)
from src.cortex.envelope import (
    AdmissionSigner,
    CortexEnvelope,
    CortexEnvelopeCodec,
    HmacAdmissionSigner,
    SignedAdmissionEnvelope,
)
from src.cortex.model_admission import (
    AdmissionDecision,
    ModelAdmissionGate,
    deploy_mode,
    is_production,
    load_engines_document,
)
from src.cortex.policy_gate import (
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
    "AdmissionDecision",
    "AdmissionSigner",
    "Approval",
    "Approvals",
    "AssetInventory",
    "BrokerBypassError",
    "BrokerDenied",
    "ChangeClass",
    "ChangeControlGate",
    "ChangeEnvelope",
    "ChangeRequest",
    "CortexBroker",
    "CortexConfig",
    "CortexEnvelope",
    "CortexEnvelopeCodec",
    "CortexPlanner",
    "CyberTaskType",
    "EngineCouncil",
    "HmacAdmissionSigner",
    "Labeled",
    "MissionEnvelope",
    "MRCReachabilityGraph",
    "ModelAdmissionGate",
    "PolicyDecision",
    "PolicyGate",
    "PolicyGateConfig",
    "PolicyVerdict",
    "ProductionDependencyError",
    "QuarantineExtractResult",
    "ReachabilityGraph",
    "ReliabilityStore",
    "SameEngineFamilyError",
    "SignedAdmissionEnvelope",
    "SignedDeviceApproval",
    "TaintSource",
    "TaintedPayload",
    "ToolCall",
    "Trust",
    "TwinStore",
    "assert_production_dependencies",
    "assert_tool_permitted",
    "build_change",
    "cross_examine",
    "deploy_mode",
    "endorse",
    "endorse_against_inventory",
    "forbidden_tool_reason",
    "injection_signal",
    "is_production",
    "load_cortex_brain_config",
    "load_cortex_config",
    "load_engines_document",
    "plan_mrc",
    "plan_mrc_reference",
    "quarantine_extract",
    "quarantine_extract_typed",
    "shield_priority",
    "spotlight_datamark",
    "standard_invariants",
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
        "AssetInventory",
        "Labeled",
        "QuarantineExtractResult",
        "TaintSource",
        "TaintedPayload",
        "Trust",
        "endorse",
        "endorse_against_inventory",
        "injection_signal",
        "quarantine_extract",
        "quarantine_extract_typed",
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
    if name in {"ReachabilityGraph", "TwinStore"}:
        from src.cortex import twin_store as _twin_store

        return getattr(_twin_store, name)
    if name in {
        "ChangeRequest",
        "build_change",
        "standard_invariants",
    }:
        from src.cortex import pccp as _pccp

        return getattr(_pccp, name)
    if name in {
        "CortexPlanner",
    }:
        from src.cortex import planner as _planner

        return getattr(_planner, name)
    if name in {
        "MRCReachabilityGraph",
        "plan_mrc",
        "plan_mrc_reference",
        "shield_priority",
    }:
        from src.cortex import reachability as _reachability

        return getattr(_reachability, name)
    if name in {
        "BrokerError",
        "EnvelopeRequired",
        "EnvelopeRejected",
        "ManifestPinMismatch",
        "XiidMCPBroker",
        "WriteEnvelope",
        "HttpMCPTransport",
        "MCPTransport",
    }:
        if name == "WriteEnvelope":
            from src.cortex.xiid_write_envelope import WriteEnvelope

            return WriteEnvelope
        if name in {"HttpMCPTransport", "MCPTransport"}:
            from src.cortex import transport_mcp as _transport_mcp

            return getattr(_transport_mcp, name)
        from src.cortex import xiid_broker as _xiid_broker

        return getattr(_xiid_broker, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
