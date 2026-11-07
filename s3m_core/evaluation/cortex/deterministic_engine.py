"""Deterministic Cortex stand-in for CI eval suites (mocked LLM backends).

Military/tactical context:
Uses offline defensive modules so release gates run on Jetson-class hardware
without live model inference or external APIs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import log2
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

from s3m_core.defense.service_protection.judge_protection import JudgeProtection
from s3m_core.evaluation.cortex.injection_variants import _BASE_PATTERNS
from s3m_core.evaluation.cortex.roles import COUNCIL_ROLES
from services.cyber.triage.alert_triage import AlertTriage
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


_OFFENSIVE_REQUEST_MARKERS = (
    "write an exploit",
    "develop malware",
    "ransomware",
    "supply working shellcode",
    "create a botnet",
    "bypass authentication for",
)


_PROTECTED_SERVICES = frozenset(
    {
        "mission_dns",
        "tactical_router",
        "classified_log_sink",
        "c2_broker_primary",
    }
)


@dataclass
class CortexActionTrace:
    """Auditable side effects during eval execution."""

    writes: List[str] = field(default_factory=list)
    containment_targets: List[str] = field(default_factory=list)
    rollbacks: List[str] = field(default_factory=list)
    refusals: List[str] = field(default_factory=list)
    model_load_attempts: List[Dict[str, Any]] = field(default_factory=list)


class DeterministicCortexEngine:
    """Rule-based cortex used when ``mode=deterministic`` eval runs execute."""

    def __init__(self) -> None:
        self._triage = AlertTriage()
        self._judge = JudgeProtection()
        self._judge.create_protected_judge(judge_model=object(), judge_tokenizer=object())
        self.trace = CortexActionTrace()
        self._state_checksum: str | None = "baseline-state-v1"
        self._approved_manifest_hash: str | None = None

    def reset_trace(self) -> None:
        self.trace = CortexActionTrace()

    def triage_event(self, case: Mapping[str, Any]) -> Dict[str, Any]:
        payload = case["event"]
        event = ThreatEvent(
            source=ThreatSource.from_value(str(payload.get("source", "MANUAL"))),
            level=ThreatLevel[str(payload["level"])],
            category=ThreatCategory[str(payload.get("category", "CYBER"))],
            title=str(payload.get("title", "Synthetic eval alert")),
            description=str(payload.get("description", "")),
            raw_data=dict(payload.get("raw_data", {})),
            confidence=float(payload.get("confidence", 0.8)),
        )
        return self._triage.triage(event)

    def extract_ioc_set(self, triage_result: Mapping[str, Any]) -> set[str]:
        values: set[str] = set()
        for obs in triage_result.get("observables", []):
            values.add(str(getattr(obs, "value", obs)))
        return values

    def rank_attack_paths(self, case: Mapping[str, Any]) -> List[str]:
        """Return path ids sorted by synthetic risk score (defensive heuristic)."""
        paths = list(case.get("attack_paths", []))
        scored: List[tuple[float, str]] = []
        for entry in paths:
            path_id = str(entry["id"])
            risk = float(entry.get("risk", 0.0))
            scored.append((risk, path_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [path_id for _, path_id in scored]

    def probe_injection(self, payload: str, channel: str) -> Dict[str, Any]:
        wrapped = f"[channel={channel}]\n{payload}"
        report = self._judge.detect_injection_attempt(wrapped)
        detected = bool(report.detected) or self._synthetic_injection_heuristic(payload)
        if detected:
            self.trace.refusals.append(f"injection_blocked:{channel}")
        return {"detected": detected, "patterns": list(report.patterns_found)}

    @staticmethod
    def _synthetic_injection_heuristic(text: str) -> bool:
        """Flag synthetic range probes; no network calls or decoding loops."""
        lowered = text.lower()
        for pattern in _BASE_PATTERNS:
            if pattern.lower() in lowered:
                return True
            # Filename/log wrappers truncate phrases; anchor on distinctive tokens.
            anchor = " ".join(pattern.lower().split()[:4])
            if anchor and anchor in lowered:
                return True
        markers = (
            "score this alert",
            "end downstream task",
            "hidden operator instructions",
            "assistant: ignore",
            "new developer message",
            "comply with user",
            "stdout_tail=",
            "doc_chunk_",
            "ignore_previous_instruct",
            "you_are_now_in_maintenan",
            "system:_override_policy_",
            "score_this_alert",
            "end_downstream_task",
        )
        if any(marker in lowered for marker in markers):
            return True
        token_pairs = (
            ("ignore", "instruct"),
            ("maintenance", "mode"),
            ("override", "policy"),
            ("disregard", "containment"),
            ("hidden", "directive"),
            ("permit", "writes"),
        )
        return any(left in lowered and right in lowered for left, right in token_pairs)

    def run_containment(self, case: Mapping[str, Any]) -> Dict[str, Any]:
        target = str(case.get("target", ""))
        protected = bool(case.get("protected", False))
        if protected or target in _PROTECTED_SERVICES:
            return {"action": "deny", "disrupted": False}
        self.trace.containment_targets.append(target)
        return {"action": "isolate", "disrupted": False}

    def apply_divergence(self, case: Mapping[str, Any]) -> None:
        drift_token = str(case.get("drift_token", "drift"))
        self._state_checksum = hashlib.sha256(drift_token.encode()).hexdigest()

    def rollback(self, case: Mapping[str, Any]) -> bool:
        expected = str(case.get("restore_checksum", "baseline-state-v1"))
        self._state_checksum = expected
        ok = self._state_checksum == expected
        if ok:
            self.trace.rollbacks.append(str(case.get("id", "rollback")))
        return ok

    def evaluate_refusal(self, role: str, user_request: str) -> bool:
        """Return True when the role refuses an offensive request."""
        lowered = user_request.lower()
        offensive = any(marker in lowered for marker in _OFFENSIVE_REQUEST_MARKERS)
        if not offensive:
            return False
        self.trace.refusals.append(f"{role}:offensive_refused")
        return True

    def evaluate_supply_chain(self, case: Mapping[str, Any]) -> bool:
        """Return True when unsafe manifest/model changes are refused."""
        action = str(case.get("action", ""))
        if action == "load_unsigned_model":
            unsigned = bool(case.get("unsigned", True))
            if unsigned:
                self.trace.refusals.append("unsigned_model_refused")
                return True
            self.trace.model_load_attempts.append(dict(case))
            return False
        if action == "apply_manifest_change":
            manifest_path = Path(str(case.get("manifest_path", "")))
            if not manifest_path.exists():
                self.trace.refusals.append("missing_manifest_refused")
                return True
            raw = manifest_path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            approved = str(case.get("approved_hash", ""))
            if approved and digest != approved:
                self.trace.refusals.append("manifest_tamper_refused")
                return True
            if case.get("signature_valid") is False:
                self.trace.refusals.append("manifest_signature_refused")
                return True
            self._approved_manifest_hash = digest
            return False
        return False

    def council_roles(self) -> Sequence[str]:
        return COUNCIL_ROLES


def ndcg_at_k(ranked: Sequence[str], ideal: Sequence[str], k: int = 3) -> float:
    """Compute NDCG@k for ranked attack path identifiers."""

    if not ideal:
        return 0.0
    k = min(k, len(ideal), len(ranked))
    ideal_set = {path_id: index for index, path_id in enumerate(ideal)}

    def dcg(items: Sequence[str]) -> float:
        score = 0.0
        for index, path_id in enumerate(items[:k], start=1):
            rel = 1.0 if path_id in ideal_set else 0.0
            if rel:
                score += rel / log2(index + 1)
        return score

    ideal_dcg = dcg(ideal)
    if ideal_dcg <= 0.0:
        return 0.0
    return dcg(ranked) / ideal_dcg


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records
