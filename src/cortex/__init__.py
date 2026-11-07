"""Cortex layer — policy gate, mission envelopes, engine council, and taint controls."""

from .envelope import CortexEnvelope, CortexEnvelopeCodec
from .policy_gate import (
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
    "Approval",
    "Approvals",
    "AssetInventory",
    "CortexEnvelope",
    "CortexEnvelopeCodec",
    "CyberTaskType",
    "EngineCouncil",
    "Labeled",
    "MissionEnvelope",
    "PolicyDecision",
    "PolicyGate",
    "PolicyVerdict",
    "QuarantineExtractResult",
    "ReliabilityStore",
    "SameEngineFamilyError",
    "ToolCall",
    "Trust",
    "cross_examine",
    "endorse",
    "endorse_against_inventory",
    "injection_signal",
    "load_cortex_config",
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
