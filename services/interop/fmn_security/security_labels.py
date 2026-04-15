"""NATO FMN security labels for coalition message dissemination."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any
from xml.etree import ElementTree as ET

from src.apps.intel.models import ReportClassification

LABEL_NAMESPACE = "urn:nato:ac322d:fmn-security-label:1.0"
ET.register_namespace("", LABEL_NAMESPACE)

_ISO3166_ALPHA3_PATTERN = re.compile(r"^[A-Z]{3}$")
_MISSION_POLICY_PATTERN = re.compile(r"^MISSION-[A-Z0-9][A-Z0-9_-]{0,63}$")

_CLASSIFICATION_RANK = {
    "NATO UNCLASSIFIED": 0,
    "NATO RESTRICTED": 1,
    "NATO CONFIDENTIAL": 2,
    "NATO SECRET": 3,
    "COSMIC TOP SECRET": 4,
}

_CLASSIFICATION_ALIASES = {
    "UNCLASSIFIED": "NATO UNCLASSIFIED",
    "NATO UNCLASSIFIED": "NATO UNCLASSIFIED",
    "FOUO": "NATO RESTRICTED",
    "RESTRICTED": "NATO RESTRICTED",
    "NATO RESTRICTED": "NATO RESTRICTED",
    "CONFIDENTIAL": "NATO CONFIDENTIAL",
    "NATO CONFIDENTIAL": "NATO CONFIDENTIAL",
    "SECRET": "NATO SECRET",
    "NATO SECRET": "NATO SECRET",
    "TOP SECRET": "COSMIC TOP SECRET",
    "COSMIC TOP SECRET": "COSMIC TOP SECRET",
}


def _normalize_token(value: str) -> str:
    return " ".join(str(value or "").strip().upper().replace("_", " ").replace("-", " ").split())


def normalize_classification(classification: str) -> str:
    """Normalize mixed military classification aliases to FMN canonical labels."""
    canonical = _CLASSIFICATION_ALIASES.get(_normalize_token(classification))
    if canonical is None:
        raise ValueError(f"Unsupported FMN classification: {classification}")
    return canonical


def classify_rank(classification: str) -> int:
    """Return numeric rank for tactical access comparisons."""
    return _CLASSIFICATION_RANK[normalize_classification(classification)]


def _normalize_policy_identifier(policy_identifier: str) -> str:
    candidate = str(policy_identifier or "").strip().upper()
    if candidate == "NATO":
        return candidate
    if _MISSION_POLICY_PATTERN.match(candidate):
        return candidate
    raise ValueError("policy_identifier must be 'NATO' or 'MISSION-{NAME}'")


def _normalize_nation_codes(codes: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_code in codes:
        code = str(raw_code or "").strip().upper()
        if not _ISO3166_ALPHA3_PATTERN.match(code):
            raise ValueError(f"Invalid ISO 3166 alpha-3 code: {raw_code}")
        if code not in normalized:
            normalized.append(code)
    return normalized


def _normalize_caveats(caveats: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in caveats:
        caveat = str(raw or "").strip().upper()
        if caveat and caveat not in normalized:
            normalized.append(caveat)
    return normalized


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


@dataclass
class NATOSecurityLabel:
    """FMN AC/322-D style security marking used across coalition data exchange."""

    classification: str
    policy_identifier: str = "NATO"
    releasable_to: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.classification = normalize_classification(self.classification)
        self.policy_identifier = _normalize_policy_identifier(self.policy_identifier)
        self.releasable_to = _normalize_nation_codes(self.releasable_to)
        self.caveats = _normalize_caveats(self.caveats)

    @classmethod
    def from_report_classification(
        cls,
        classification: ReportClassification,
        *,
        policy_identifier: str = "NATO",
        releasable_to: list[str] | None = None,
        caveats: list[str] | None = None,
    ) -> "NATOSecurityLabel":
        """Bridge existing report classification enums into FMN labels."""
        return cls(
            classification=classification.value,
            policy_identifier=policy_identifier,
            releasable_to=releasable_to or [],
            caveats=caveats or [],
        )

    def build_label(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "policy_identifier": self.policy_identifier,
            "releasable_to": list(self.releasable_to),
            "caveats": list(self.caveats),
        }

    def to_xml(self) -> str:
        """Serialize according to NATO label XML binding shape."""
        root = ET.Element(f"{{{LABEL_NAMESPACE}}}SecurityLabel")
        ET.SubElement(root, f"{{{LABEL_NAMESPACE}}}Classification").text = self.classification
        ET.SubElement(root, f"{{{LABEL_NAMESPACE}}}PolicyIdentifier").text = self.policy_identifier

        releasable_node = ET.SubElement(root, f"{{{LABEL_NAMESPACE}}}ReleasableTo")
        for nation in self.releasable_to:
            ET.SubElement(releasable_node, f"{{{LABEL_NAMESPACE}}}Nation").text = nation

        caveats_node = ET.SubElement(root, f"{{{LABEL_NAMESPACE}}}Caveats")
        for caveat in self.caveats:
            ET.SubElement(caveats_node, f"{{{LABEL_NAMESPACE}}}Caveat").text = caveat

        return ET.tostring(root, encoding="unicode")

    @classmethod
    def from_xml(cls, xml_str: str) -> "NATOSecurityLabel":
        """Parse NATO security label XML into a typed model."""
        if not str(xml_str or "").strip():
            raise ValueError("xml_str is required")

        root = ET.fromstring(xml_str)
        if _local_name(root.tag) != "SecurityLabel":
            raise ValueError("Expected SecurityLabel root element")

        classification = ""
        policy_identifier = "NATO"
        releasable_to: list[str] = []
        caveats: list[str] = []

        for child in root:
            local_tag = _local_name(child.tag)
            if local_tag == "Classification":
                classification = str(child.text or "").strip()
            elif local_tag == "PolicyIdentifier":
                policy_identifier = str(child.text or "").strip() or "NATO"
            elif local_tag == "ReleasableTo":
                releasable_to = [
                    str(grandchild.text or "").strip()
                    for grandchild in child
                    if _local_name(grandchild.tag) == "Nation"
                ]
            elif local_tag == "Caveats":
                caveats = [
                    str(grandchild.text or "").strip()
                    for grandchild in child
                    if _local_name(grandchild.tag) == "Caveat"
                ]

        return cls(
            classification=classification,
            policy_identifier=policy_identifier,
            releasable_to=releasable_to,
            caveats=caveats,
        )

    def validate_access(self, user_clearance: str, user_nation: str) -> bool:
        """Check coalition release eligibility for a requesting operator."""
        try:
            user_rank = classify_rank(user_clearance)
        except ValueError:
            return False

        nation = str(user_nation or "").strip().upper()
        if not _ISO3166_ALPHA3_PATTERN.match(nation):
            return False

        if user_rank < classify_rank(self.classification):
            return False

        if self.releasable_to and nation not in self.releasable_to:
            return False

        for caveat in self.caveats:
            if caveat == "NOFORN" and nation != "USA":
                return False
            if caveat.startswith("REL TO "):
                targets = [chunk.strip() for chunk in re.split(r"[,;/]", caveat[7:]) if chunk.strip()]
                try:
                    target_codes = _normalize_nation_codes(targets)
                except ValueError:
                    return False
                if target_codes and nation not in target_codes:
                    return False

        return True
