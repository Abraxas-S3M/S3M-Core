"""Adversarial Cross-Examination (ACE) for cyber analytic conclusions.

Military/tactical context: contested cyber assessments require a proposer and an
independent challenger from different model families so prompt injection or
single-model bias cannot dominate the SOC recommendation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Set

logger = logging.getLogger("s3m.cortex.ace")

CLAIM_LINE_PATTERN = re.compile(
    r"^CLAIM\|(?P<evidence>[^|]*)\|(?P<text>.+)$",
    re.MULTILINE,
)


class CouncilEngineCallable(Protocol):
    """Minimal engine surface used by ACE (mocked in unit tests)."""

    role: str
    family: str
    engine_id: str

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


@dataclass
class ACEClaim:
    text: str
    evidence_ids: List[str] = field(default_factory=list)
    accepted: bool = True


@dataclass
class ACEResult:
    """Outcome of ACE: grounded claims and synthesized recommendation text."""

    recommendation: str
    claims: List[ACEClaim]
    proposer_role: str
    challenger_role: str
    dropped_ungrounded: int
    evidence_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "claims": [
                {"text": c.text, "evidence_ids": c.evidence_ids, "accepted": c.accepted}
                for c in self.claims
            ],
            "proposer_role": self.proposer_role,
            "challenger_role": self.challenger_role,
            "dropped_ungrounded": self.dropped_ungrounded,
            "evidence_ids": self.evidence_ids,
        }


class SameEngineFamilyError(ValueError):
    """Raised when ACE proposer and challenger share a model family."""


def assert_distinct_families(proposer: CouncilEngineCallable, challenger: CouncilEngineCallable) -> None:
    if (proposer.family or "").strip().lower() == (challenger.family or "").strip().lower():
        raise SameEngineFamilyError(
            f"ACE requires distinct model families; both are '{proposer.family}' "
            f"({proposer.role} vs {challenger.role})"
        )


def parse_claims(response_text: str) -> List[ACEClaim]:
    """Parse CLAIM|evidence_id,...|text lines from engine output."""
    claims: List[ACEClaim] = []
    for match in CLAIM_LINE_PATTERN.finditer(response_text or ""):
        evidence_raw = match.group("evidence").strip()
        evidence_ids = [part.strip() for part in evidence_raw.split(",") if part.strip()]
        claims.append(ACEClaim(text=match.group("text").strip(), evidence_ids=evidence_ids))
    return claims


def filter_grounded_claims(
    claims: Iterable[ACEClaim],
    allowed_evidence: Set[str],
) -> tuple[List[ACEClaim], int]:
    """Drop claims that cite no evidence or cite IDs outside the case bundle."""
    kept: List[ACEClaim] = []
    dropped = 0
    for claim in claims:
        if not claim.evidence_ids:
            dropped += 1
            continue
        if not all(eid in allowed_evidence for eid in claim.evidence_ids):
            dropped += 1
            continue
        kept.append(claim)
    return kept, dropped


class ReliabilityStore:
    """Persistent per-engine reliability scores for human feedback loops."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._table: Dict[str, Dict[str, Dict[str, float | int]]] = {}
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            self._table = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Reliability table load failed: %s", exc)
            self._table = {}
            return
        engines = payload.get("engines", {})
        if isinstance(engines, dict):
            self._table = engines  # type: ignore[assignment]
        else:
            self._table = {}

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"engines": self._table}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def record_verdict(self, engine_id: str, domain: str, correct: bool) -> None:
        engine_bucket = self._table.setdefault(engine_id, {})
        domain_bucket = engine_bucket.setdefault(
            domain,
            {"correct": 0, "total": 0, "score": 0.0},
        )
        domain_bucket["total"] = int(domain_bucket.get("total", 0)) + 1
        if correct:
            domain_bucket["correct"] = int(domain_bucket.get("correct", 0)) + 1
        total = max(1, int(domain_bucket["total"]))
        domain_bucket["score"] = float(domain_bucket.get("correct", 0)) / total
        self.persist()

    def get_score(self, engine_id: str, domain: str) -> float:
        return float(self._table.get(engine_id, {}).get(domain, {}).get("score", 0.0))

    def snapshot(self) -> Dict[str, Dict[str, Dict[str, float | int]]]:
        return json.loads(json.dumps(self._table))


def cross_examine(
    *,
    evidence_ids: List[str],
    case_evidence: Mapping[str, str],
    proposer: CouncilEngineCallable,
    challenger: CouncilEngineCallable,
    reliability: ReliabilityStore,
    system_prompt: str,
    user_prompt: str,
    task_domain: str = "cyber",
) -> ACEResult:
    """
    Run ACE: proposer drafts grounded claims; challenger stress-tests; ungrounded
    claims are removed before the recommendation is returned.
    """
    assert_distinct_families(proposer, challenger)
    allowed = set(evidence_ids)

    proposer_out = proposer.complete(system_prompt, user_prompt)
    raw_claims = parse_claims(proposer_out)
    grounded, dropped = filter_grounded_claims(raw_claims, allowed)

    challenge_prompt = user_prompt + "\n\n" + _format_claims_for_challenge(grounded)
    challenger_out = challenger.complete(system_prompt, challenge_prompt)
    refuted = _parse_refutations(challenger_out)

    final_claims: List[ACEClaim] = []
    for claim in grounded:
        if claim.text in refuted:
            claim.accepted = False
        final_claims.append(claim)

    accepted_texts = [c.text for c in final_claims if c.accepted]
    if accepted_texts:
        recommendation = "ACE recommendation:\n" + "\n".join(f"- {line}" for line in accepted_texts)
    else:
        recommendation = "ACE recommendation: insufficient grounded evidence; escalate to analyst."

    # Nudge reliability table toward proposer engine (feedback can correct later).
    reliability.record_verdict(proposer.engine_id, task_domain, bool(accepted_texts))

    return ACEResult(
        recommendation=recommendation,
        claims=final_claims,
        proposer_role=proposer.role,
        challenger_role=challenger.role,
        dropped_ungrounded=dropped,
        evidence_ids=list(evidence_ids),
    )


def _format_claims_for_challenge(claims: List[ACEClaim]) -> str:
    if not claims:
        return "PROPOSER_CLAIMS: (none grounded)"
    lines = ["PROPOSER_CLAIMS:"]
    for claim in claims:
        ev = ",".join(claim.evidence_ids)
        lines.append(f"CLAIM|{ev}|{claim.text}")
    return "\n".join(lines)


def _parse_refutations(challenger_text: str) -> Set[str]:
    refuted: Set[str] = set()
    for line in (challenger_text or "").splitlines():
        line = line.strip()
        if line.upper().startswith("REFUTE|"):
            parts = line.split("|", 2)
            if len(parts) == 3:
                refuted.add(parts[2].strip())
    return refuted
