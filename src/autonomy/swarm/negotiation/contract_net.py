"""
S3M FIPA Contract Net protocol implementation.

Implements decentralized tactical task negotiation where a manager agent issues
CFPs and participant agents bid with multi-attribute proposals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
import uuid

from pydantic import BaseModel, Field, field_validator

from src.autonomy.arbitration.consensus_protocol import ByzantineConsensus

if TYPE_CHECKING:
    from src.autonomy.arbitration.arbitrator import MultiAgentArbitrator
    from src.autonomy.models import AgentInfo, Mission
    from src.autonomy.swarm.coordinator import SwarmCoordinator


LOGGER = logging.getLogger(__name__)


class ProposalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REFUSED = "refused"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class CallForProposal(BaseModel):
    """Manager request for proposals for a tactical task."""

    cfp_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_id: str
    task_description: str = ""
    required_capabilities: List[str] = Field(default_factory=list)
    deadline_ms: float = Field(default=5000.0, gt=0.0)
    evaluation_criteria: Dict[str, float] = Field(
        default_factory=lambda: {"cost": 0.3, "time": 0.3, "capability": 0.4}
    )
    min_proposals: int = Field(default=1, ge=1)
    issued_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    issuer_id: str = "system"

    @field_validator("evaluation_criteria")
    @classmethod
    def _validate_criteria(cls, value: Dict[str, float]) -> Dict[str, float]:
        if not value:
            raise ValueError("evaluation_criteria must not be empty")
        cleaned = {str(k): float(v) for k, v in value.items()}
        if any(v < 0.0 for v in cleaned.values()):
            raise ValueError("evaluation criteria weights must be non-negative")
        if sum(cleaned.values()) <= 0.0:
            raise ValueError("evaluation criteria weights must sum to > 0")
        return cleaned


class Proposal(BaseModel):
    """Participant proposal for a CFP."""

    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    cfp_id: str
    agent_id: str
    coalition_ids: List[str] = Field(default_factory=list)
    cost_estimate: float = Field(default=0.0, ge=0.0)
    time_estimate_ms: float = Field(default=0.0, ge=0.0)
    capability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    custom_attributes: Dict[str, float] = Field(default_factory=dict)
    status: ProposalStatus = ProposalStatus.PENDING
    submitted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("custom_attributes")
    @classmethod
    def _sanitize_custom_attributes(cls, value: Dict[str, float]) -> Dict[str, float]:
        return {str(k): float(v) for k, v in value.items()}


class NegotiationRound(BaseModel):
    """Recorded round details for after-action review."""

    round_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    cfp: CallForProposal
    proposals: List[Proposal] = Field(default_factory=list)
    winner: Optional[str] = None
    winner_score: float = 0.0
    elapsed_ms: float = 0.0


class NegotiationResult(BaseModel):
    """Final tactical negotiation outcome."""

    task_id: str
    success: bool
    winner_agent_id: Optional[str] = None
    winner_coalition: List[str] = Field(default_factory=list)
    winning_proposal: Optional[Proposal] = None
    rounds_completed: int = 0
    total_proposals: int = 0
    rationale_en: str = ""
    rationale_ar: str = ""
    arbitration_summary: Dict[str, Any] = Field(default_factory=dict)


class ContractNetProtocol:
    """
    Thread-safe FIPA Contract Net manager for swarm negotiation.

    Tactical context: this module enables decentralized role bidding so mission
    command can still allocate work if central planning links degrade.
    """

    def __init__(self, max_rounds: int = 3) -> None:
        self._max_rounds = max(1, int(max_rounds))
        self._cfps: Dict[str, CallForProposal] = {}
        self._proposals: Dict[str, List[Proposal]] = {}
        self._rounds: List[NegotiationRound] = []
        self._results_by_task: Dict[str, NegotiationResult] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._consensus = ByzantineConsensus()
        self._lock = threading.RLock()

    def _log_bilingual(self, message_en: str, message_ar: str, **payload: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_en": message_en,
            "message_ar": message_ar,
            "payload": dict(payload),
        }
        self._audit_log.append(entry)
        if len(self._audit_log) > 5000:
            self._audit_log = self._audit_log[-5000:]
        LOGGER.info("%s | %s | payload=%s", message_en, message_ar, payload)

    @staticmethod
    def _parse_iso_ms(timestamp: str) -> float:
        return datetime.fromisoformat(timestamp).timestamp() * 1000.0

    def create_cfp(
        self,
        task_id: str,
        task_description: str = "",
        required_capabilities: Optional[List[str]] = None,
        evaluation_criteria: Optional[Dict[str, float]] = None,
        deadline_ms: float = 5000.0,
        issuer_id: str = "system",
        min_proposals: int = 1,
    ) -> CallForProposal:
        """Create and register a new call-for-proposal."""
        cfp = CallForProposal(
            task_id=str(task_id),
            task_description=str(task_description),
            required_capabilities=list(required_capabilities or []),
            evaluation_criteria=evaluation_criteria or {"cost": 0.3, "time": 0.3, "capability": 0.4},
            deadline_ms=float(deadline_ms),
            issuer_id=str(issuer_id),
            min_proposals=int(min_proposals),
        )
        with self._lock:
            self._cfps[cfp.cfp_id] = cfp
            self._proposals[cfp.cfp_id] = []
            self._log_bilingual(
                "CFP created",
                "تم إنشاء طلب عروض",
                cfp_id=cfp.cfp_id,
                task_id=cfp.task_id,
                issuer_id=cfp.issuer_id,
            )
        return cfp

    def create_cfp_from_mission(
        self,
        mission: "Mission",
        issuer_id: str = "swarm_coordinator",
        deadline_ms: float = 5000.0,
    ) -> CallForProposal:
        """Build a CFP directly from an existing mission definition."""
        required_caps = mission.parameters.get("required_capabilities", [])
        if isinstance(required_caps, str):
            required_caps = [required_caps]
        return self.create_cfp(
            task_id=mission.mission_id,
            task_description=mission.description,
            required_capabilities=[str(cap) for cap in required_caps],
            deadline_ms=deadline_ms,
            issuer_id=issuer_id,
            min_proposals=int(mission.parameters.get("min_proposals", 1)),
        )

    def submit_proposal(self, cfp_id: str, proposal: Proposal) -> bool:
        """Submit a proposal for a known CFP."""
        with self._lock:
            cfp = self._cfps.get(cfp_id)
            if cfp is None:
                self._log_bilingual(
                    "Proposal rejected: CFP missing",
                    "تم رفض العرض: طلب العروض غير موجود",
                    cfp_id=cfp_id,
                    agent_id=proposal.agent_id,
                )
                return False

            now_ms = time.time() * 1000.0
            issued_ms = self._parse_iso_ms(cfp.issued_at)
            if now_ms - issued_ms > cfp.deadline_ms:
                proposal.status = ProposalStatus.EXPIRED
                self._log_bilingual(
                    "Proposal expired at submission",
                    "انتهت صلاحية العرض عند الإرسال",
                    cfp_id=cfp_id,
                    agent_id=proposal.agent_id,
                )
                return False

            proposal.cfp_id = cfp_id
            self._proposals[cfp_id].append(proposal)
            self._log_bilingual(
                "Proposal submitted",
                "تم تقديم العرض",
                cfp_id=cfp_id,
                proposal_id=proposal.proposal_id,
                agent_id=proposal.agent_id,
            )
            return True

    def bootstrap_proposals_from_swarm(self, cfp_id: str, coordinator: "SwarmCoordinator") -> int:
        """
        Generate baseline proposals from registered swarm agents.

        Tactical context: this fallback allows mission bidding even when explicit
        participant-side proposal agents are not running on all platforms.
        """
        with self._lock:
            if cfp_id not in self._cfps:
                return 0
            cfp = self._cfps[cfp_id]

        submitted = 0
        for agent in coordinator.get_agents():
            if not agent.is_available():
                continue
            capability_match = 1.0
            if cfp.required_capabilities:
                capability_match = 1.0 if agent.capability.value in cfp.required_capabilities else 0.4
            proposal = Proposal(
                cfp_id=cfp_id,
                agent_id=agent.agent_id,
                cost_estimate=max(1.0, 100.0 - agent.battery_pct),
                time_estimate_ms=max(1000.0, agent.distance_to(0.0, 0.0, 0.0) * 15.0),
                capability_score=max(0.0, min(1.0, capability_match * (agent.battery_pct / 100.0))),
            )
            if self.submit_proposal(cfp_id, proposal):
                submitted += 1
        return submitted

    def _score_proposal(self, proposal: Proposal, criteria: Dict[str, float], deadline_ms: float) -> float:
        total = sum(criteria.values()) or 1.0
        weights = {k: v / total for k, v in criteria.items()}
        score = 0.0

        # Lower resource burden preserves combat power for follow-on tasks.
        cost_score = 1.0 / (1.0 + proposal.cost_estimate / 100.0)
        score += weights.get("cost", 0.0) * cost_score

        # Deadline-aware timing score penalizes bids that exceed timing windows.
        raw_time = 1.0 / (1.0 + proposal.time_estimate_ms / 10000.0)
        if proposal.time_estimate_ms > deadline_ms:
            raw_time *= max(0.1, deadline_ms / proposal.time_estimate_ms)
        score += weights.get("time", 0.0) * raw_time

        score += weights.get("capability", 0.0) * proposal.capability_score

        for attr, val in proposal.custom_attributes.items():
            if attr in weights:
                score += weights[attr] * max(0.0, min(1.0, float(val)))
        return max(0.0, min(1.0, score))

    def evaluate_and_award(
        self,
        cfp_id: str,
        consensus_nodes: Optional[List[str]] = None,
        consensus_votes: Optional[Dict[str, str]] = None,
    ) -> NegotiationResult:
        """Evaluate active proposals and select the best bidder."""
        start = time.perf_counter()
        with self._lock:
            cfp = self._cfps.get(cfp_id)
            if cfp is None:
                return NegotiationResult(task_id="unknown", success=False, rationale_en="CFP not found")

            proposals = self._proposals.get(cfp_id, [])
            active = [p for p in proposals if p.status == ProposalStatus.PENDING]
            if len(active) < cfp.min_proposals:
                result = NegotiationResult(
                    task_id=cfp.task_id,
                    success=False,
                    total_proposals=len(active),
                    rationale_en=f"Insufficient proposals: {len(active)} < {cfp.min_proposals}",
                    rationale_ar=f"عدد العروض غير كافٍ: {len(active)} < {cfp.min_proposals}",
                )
                self._results_by_task[cfp.task_id] = result
                return result

            if consensus_nodes:
                votes = consensus_votes or {node: "approve" for node in consensus_nodes}
                consensus_result = self._consensus.run_consensus(
                    nodes=consensus_nodes,
                    votes=votes,
                    proposal_id=cfp.cfp_id,
                )
                if not bool(consensus_result.get("approved", False)):
                    result = NegotiationResult(
                        task_id=cfp.task_id,
                        success=False,
                        total_proposals=len(active),
                        rationale_en="Consensus rejected award.",
                        rationale_ar="تم رفض الإرساء عبر آلية الإجماع.",
                        arbitration_summary={"consensus": consensus_result},
                    )
                    self._results_by_task[cfp.task_id] = result
                    return result

            scored: List[Tuple[Proposal, float]] = []
            for proposal in active:
                score = self._score_proposal(proposal, cfp.evaluation_criteria, cfp.deadline_ms)
                scored.append((proposal, score))
            scored.sort(key=lambda item: item[1], reverse=True)

            winner_prop, winner_score = scored[0]
            winner_prop.status = ProposalStatus.ACCEPTED
            for proposal, _ in scored[1:]:
                proposal.status = ProposalStatus.REJECTED

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._rounds.append(
                NegotiationRound(
                    cfp=cfp,
                    proposals=[proposal for proposal in active],
                    winner=winner_prop.agent_id,
                    winner_score=winner_score,
                    elapsed_ms=elapsed_ms,
                )
            )

            alternatives = ", ".join(f"{proposal.agent_id}({score:.3f})" for proposal, score in scored[1:4])
            result = NegotiationResult(
                task_id=cfp.task_id,
                success=True,
                winner_agent_id=winner_prop.agent_id,
                winner_coalition=list(winner_prop.coalition_ids),
                winning_proposal=winner_prop,
                rounds_completed=1,
                total_proposals=len(active),
                rationale_en=(
                    f"Agent '{winner_prop.agent_id}' won task '{cfp.task_id}' with score "
                    f"{winner_score:.4f}. Alternatives: [{alternatives}]."
                ),
                rationale_ar=(
                    f"فاز الوكيل '{winner_prop.agent_id}' بالمهمة '{cfp.task_id}' بدرجة "
                    f"{winner_score:.4f}. البدائل: [{alternatives}]."
                ),
            )
            self._results_by_task[cfp.task_id] = result
            self._log_bilingual(
                "Negotiation awarded",
                "تم إرساء التفاوض",
                cfp_id=cfp_id,
                winner=winner_prop.agent_id,
                score=winner_score,
            )
            return result

    def evaluate_with_arbitrator(
        self,
        cfp_id: str,
        arbitrator: "MultiAgentArbitrator",
        agents: List["AgentInfo"],
        mode: str = "coalition",
    ) -> NegotiationResult:
        """
        Evaluate CFP and cross-check assignment consistency with arbitrator.

        Tactical context: combining contract-net and arbitration provides
        robustness against single-method allocation bias under battlefield load.
        """
        result = self.evaluate_and_award(cfp_id)
        if not result.success:
            return result

        with self._lock:
            cfp = self._cfps.get(cfp_id)
            if cfp is None:
                return result

        arbitration = arbitrator.arbitrate(
            mission={"mission_id": cfp.task_id, "objectives": [cfp.task_id]},
            agents=agents,
            mode=mode,
        )
        result.arbitration_summary = {
            "mode": arbitration.get("mode"),
            "assignments": arbitration.get("assignments", {}),
            "consensus": arbitration.get("consensus_result", {}),
        }
        return result

    def get_history(self) -> List[NegotiationRound]:
        with self._lock:
            return list(self._rounds)

    def get_result(self, task_id: str) -> Optional[NegotiationResult]:
        with self._lock:
            return self._results_by_task.get(task_id)

    def get_audit_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._audit_log)
