"""Cyber cortex council — task-typed routing and adversarial cross-examination."""

__all__ = [
    "ACEResult",
    "CyberTaskType",
    "EngineCouncil",
    "QuarantineExtractResult",
    "ReliabilityStore",
    "SameEngineFamilyError",
    "cross_examine",
    "load_cortex_config",
    "quarantine_extract",
    "spotlight_datamark",
]


def __getattr__(name: str):
    """Lazy exports avoid pulling optional API dependencies at import time."""
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
