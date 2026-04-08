"""SIDC generation helpers for tactical track symbology.

This module emits deterministic 20-digit NATO SIDC-like identifiers so the
COP can render consistent symbols even when upstream tracks are incomplete.
"""

from __future__ import annotations

from typing import Optional

AFFILIATION_CODE_MAP = {
    "friendly": "3",
    "hostile": "6",
    "unknown": "1",
}

DOMAIN_CODE_MAP = {
    "land": "1",
    "ground": "1",
    "kinetic": "2",
    "air": "3",
    "maritime": "4",
    "sea": "4",
    "subsurface": "5",
    "space": "6",
    "cyber": "7",
    "intel": "8",
    "electronic": "9",
}

_SIDC_PREFIX = "100"
_SIDC_SUFFIX = "000000000000000"


def generate_sidc(
    affiliation: Optional[str],
    domain: Optional[str],
    entity_type: Optional[str],
) -> str:
    """Generate a deterministic 20-digit SIDC string for a track."""

    normalized_affiliation = _normalize_affiliation(affiliation)
    normalized_domain = _normalize_domain(domain=domain, entity_type=entity_type)
    aff_code = AFFILIATION_CODE_MAP.get(normalized_affiliation, AFFILIATION_CODE_MAP["unknown"])
    domain_code = DOMAIN_CODE_MAP.get(normalized_domain, "0")
    sidc = f"{_SIDC_PREFIX}{aff_code}{domain_code}{_SIDC_SUFFIX}"
    return sidc if sidc.isdigit() and len(sidc) == 20 else "10010000000000000000"


def _normalize_affiliation(raw_affiliation: Optional[str]) -> str:
    value = str(raw_affiliation or "").strip().lower()
    if value in {"friendly", "friend", "blue", "own", "ally", "allied"}:
        return "friendly"
    if value in {"hostile", "enemy", "adversary", "red"}:
        return "hostile"
    return "unknown"


def _normalize_domain(domain: Optional[str], entity_type: Optional[str]) -> str:
    raw_domain = str(domain or "").strip().lower()
    if raw_domain in DOMAIN_CODE_MAP:
        return raw_domain

    raw_entity_type = str(entity_type or "").strip().lower()
    if any(token in raw_entity_type for token in ("uav", "air", "aircraft", "missile", "jet")):
        return "air"
    if any(token in raw_entity_type for token in ("cyber", "network", "packet")):
        return "cyber"
    if any(token in raw_entity_type for token in ("intel", "sigint", "elint", "humint")):
        return "intel"
    if any(token in raw_entity_type for token in ("ship", "vessel", "boat", "naval", "sea")):
        return "maritime"
    if any(token in raw_entity_type for token in ("sub", "submarine", "subsurface")):
        return "subsurface"
    if any(token in raw_entity_type for token in ("space", "satellite", "orbital")):
        return "space"
    return "kinetic"
