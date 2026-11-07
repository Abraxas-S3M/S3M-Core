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
    "ChangeClass",
    "ChangeControlGate",
    "ChangeEnvelope",
    "SignedDeviceApproval",
    "CortexEnvelope",
    "CortexEnvelopeCodec",
    "CyberTaskType",
    "EngineCouncil",
    "HmacAdmissionSigner",
    "Labeled",
    "MissionEnvelope",
    "ModelAdmissionGate",
    "PolicyDecision",
    "PolicyGate",
    "PolicyVerdict",
    "QuarantineExtractResult",
    "ReliabilityStore",
    "SameEngineFamilyError",
    "SignedAdmissionEnvelope",
    "ToolCall",
    "Trust",
    "cross_examine",
    "deploy_mode",
    "endorse",
    "endorse_against_inventory",
    "injection_signal",
    "is_production",
    "load_cortex_config",
    "load_engines_document",
    "quarantine_extract",
    "quarantine_extract_typed",
    "spotlight_datamark",
]


def __getattr__(name: str):
    """Lazy exports for cyber council modules (optional API deps stay unloaded)."""
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
        "Trust",
        "endorse",
        "endorse_against_inventory",
        "injection_signal",
        "quarantine_extract",
        "quarantine_extract_typed",
        "spotlight_datamark",
    }:
        from src.cortex import taint as _taint

        return getattr(_taint, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
