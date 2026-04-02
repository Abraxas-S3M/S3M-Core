"""
Process-level micro-segmentation for S3M inter-layer communication.
Only explicitly authorized layer-to-layer, process-to-process connections
are permitted. All other traffic is denied by default (zero-trust).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class AccessVerdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    AUDIT = "AUDIT"


@dataclass
class SegmentRule:
    """A single micro-segmentation policy rule."""

    rule_id: str
    source_layer: str
    source_process: str  # "*" for any process in the layer
    destination_layer: str
    destination_process: str
    verdict: AccessVerdict = AccessVerdict.ALLOW
    description: str = ""
    bidirectional: bool = False


class MicroSegmentationPolicy:
    """Enforces process-level isolation between S3M layers.

    Default-deny: if no rule explicitly allows a connection, it is blocked.
    This prevents lateral movement even if an attacker compromises one layer.

    Pre-loaded with the S3M canonical OODA data flow:
      Sensors -> Layer 02 -> Layer 01 -> Layer 03 -> Layer 04
      Layer 05 <-> Layer 03
      Layer 06 -> all (read-only)
      Layer 07 <- Layer 02 (threat feed)
      Layer 08 -> Layer 02, Layer 06 (intel extraction)
    """

    def __init__(self, custom_rules: Optional[List[SegmentRule]] = None) -> None:
        self._rules: List[SegmentRule] = []
        self._load_default_rules()
        if custom_rules:
            self._rules.extend(custom_rules)

    def _load_default_rules(self) -> None:
        defaults = [
            SegmentRule("r001", "layer-02-threat", "suricata_adapter", "layer-01-llm", "orchestrator", description="Threat->LLM assessment"),
            SegmentRule("r002", "layer-02-threat", "wazuh_adapter", "layer-01-llm", "orchestrator", description="SIEM->LLM assessment"),
            SegmentRule("r003", "layer-01-llm", "orchestrator", "layer-03-autonomy", "*", description="LLM decisions->Autonomy"),
            SegmentRule("r004", "layer-03-autonomy", "*", "layer-04-simulation", "*", description="Autonomy<->Simulation", bidirectional=True),
            SegmentRule("r005", "layer-05-navigation", "*", "layer-03-autonomy", "*", description="Nav<->Autonomy", bidirectional=True),
            SegmentRule("r006", "layer-06-dashboard", "*", "*", "*", verdict=AccessVerdict.ALLOW, description="Dashboard read-only access"),
            SegmentRule("r007", "layer-02-threat", "threat_manager", "layer-07-cyber", "soc_manager", description="Threats->SOC"),
            SegmentRule("r008", "layer-08-comms", "intel_extractor", "layer-02-threat", "threat_manager", description="Comms intel->Threat"),
            SegmentRule("r009", "layer-08-comms", "*", "layer-06-dashboard", "*", description="Comms->Dashboard"),
            SegmentRule("r010", "layer-10-security", "*", "*", "*", description="Security shell->all layers"),
            SegmentRule("r011", "layer-01-llm", "allam", "layer-08-comms", "arabic_nlp", description="ALLaM<->Arabic NLP", bidirectional=True),
        ]
        self._rules.extend(defaults)

    def evaluate(
        self, source_layer: str, source_process: str,
        dest_layer: str, dest_process: str,
    ) -> AccessVerdict:
        """Evaluate a connection request. Default: DENY."""
        for rule in self._rules:
            if self._match(rule, source_layer, source_process, dest_layer, dest_process):
                return rule.verdict
            if rule.bidirectional and self._match(
                rule, dest_layer, dest_process, source_layer, source_process
            ):
                return rule.verdict
        return AccessVerdict.DENY

    def _match(
        self, rule: SegmentRule, src_layer: str, src_proc: str,
        dst_layer: str, dst_proc: str,
    ) -> bool:
        if rule.source_layer != "*" and rule.source_layer != src_layer:
            return False
        if rule.source_process != "*" and rule.source_process != src_proc:
            return False
        if rule.destination_layer != "*" and rule.destination_layer != dst_layer:
            return False
        if rule.destination_process != "*" and rule.destination_process != dst_proc:
            return False
        return True

    def add_rule(self, rule: SegmentRule) -> None:
        self._rules.append(rule)

    def list_rules(self) -> List[Dict[str, str]]:
        return [
            {
                "rule_id": r.rule_id,
                "source": f"{r.source_layer}/{r.source_process}",
                "destination": f"{r.destination_layer}/{r.destination_process}",
                "verdict": r.verdict.value,
                "description": r.description,
            }
            for r in self._rules
        ]
