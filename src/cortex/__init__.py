"""Cortex input taint and provenance controls for tactical LLM boundaries."""

from src.cortex.taint import (
    Labeled,
    Trust,
    endorse,
    endorse_against_inventory,
    injection_signal,
    quarantine_extract,
)

__all__ = [
    "Labeled",
    "Trust",
    "endorse",
    "endorse_against_inventory",
    "injection_signal",
    "quarantine_extract",
]
