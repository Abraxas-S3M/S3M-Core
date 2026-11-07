"""Cortex layer — policy gate, mission envelopes, engine council, and admission."""

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
from src.cortex.policy_gate import Approval, MissionEnvelope, PolicyGate, PolicyVerdict

__all__ = [
    "ACEResult",
    "AdmissionDecision",
    "AdmissionSigner",
    "Approval",
    "CortexEnvelope",
    "CortexEnvelopeCodec",
    "CyberTaskType",
    "EngineCouncil",
    "HmacAdmissionSigner",
    "MissionEnvelope",
    "ModelAdmissionGate",
    "PolicyGate",
    "PolicyVerdict",
    "QuarantineExtractResult",
    "ReliabilityStore",
    "SameEngineFamilyError",
    "SignedAdmissionEnvelope",
    "cross_examine",
    "deploy_mode",
    "is_production",
    "load_cortex_config",
    "load_engines_document",
    "quarantine_extract",
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
    if name in {"QuarantineExtractResult", "quarantine_extract", "spotlight_datamark"}:
        from src.cortex import taint as _taint

        return getattr(_taint, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
