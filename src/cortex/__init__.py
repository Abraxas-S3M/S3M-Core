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
    "BindingSource",
    "BrokerBypassError",
    "BrokerDenied",
    "ChangeClass",
    "ChangeControlGate",
    "ChangeEnvelope",
    "CortexBroker",
    "CortexConfig",
    "CortexMissionService",
    "CortexEnvelope",
    "CortexEnvelopeCodec",
    "CyberTaskType",
    "EngineCouncil",
    "HmacAdmissionSigner",
    "MissionBinding",
    "MissionEnvelope",
    "MissionFlow",
    "MinimalProfilePlan",
    "ModelAdmissionGate",
    "NetworkEdge",
    "NetworkTwin",
    "PCCPChange",
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
    "TwinStore",
    "assert_production_dependencies",
    "assert_tool_permitted",
    "cross_examine",
    "deploy_mode",
    "forbidden_tool_reason",
    "is_production",
    "load_cortex_brain_config",
    "load_cortex_config",
    "load_engines_document",
    "load_mission_cortex_settings",
    "mission_weight",
    "quarantine_extract",
    "spotlight_datamark",
    "wrap_untrusted",
]


def __getattr__(name: str):
    """Lazy exports for cyber council, brain-upgrade, and mission-twin modules."""
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
    if name in {"ReachabilityGraph", "TwinStore"}:
        from src.cortex import twin_store as _twin_store

        return getattr(_twin_store, name)
    if name in {
        "BindingSource",
        "CortexMissionService",
        "MissionBinding",
        "MissionFlow",
        "MinimalProfilePlan",
        "NetworkEdge",
        "NetworkTwin",
        "PCCPChange",
    }:
        from src.cortex import models as _models
        from src.cortex.service import CortexMissionService
        from src.cortex.twin import NetworkTwin

        if name == "CortexMissionService":
            return CortexMissionService
        if name == "NetworkTwin":
            return NetworkTwin
        return getattr(_models, name)
    if name in {"load_mission_cortex_settings", "mission_weight"}:
        from src.cortex import mission_config as _mission_config

        return getattr(_mission_config, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
