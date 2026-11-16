"""Cortex autonomous defense cycle: discover -> twin -> architect -> approve -> execute -> verify.

Military/tactical context:
One bounded, auditable loop that turns XiiD inventory into a verified security change.
The AI layer never holds write authority: every mutation needs (1) out-of-band device
approvals recorded by the existing ApprovalService / ChangeControlGate, (2) an operator
WriteEnvelope bound to the exact tool arguments with an expiry, and (3) the XiiD MCP
broker, which re-checks the pinned tool manifest on every call.

Execution safety rules:
* Reversible changes run first; each is verified against *observed* XiiD state before
  the next one runs. Irreversible changes run last, only if everything before verified.
* On any postcondition failure: stop, roll back executed reversible changes in reverse
  order using rollback envelopes approved together with the change, verify the
  restoration, and escalate. Irreversible changes are never "rolled back" by guesswork.
* Irreversible changes are escalated to class D (two distinct approvers).

Honesty labels are written into every report: this cycle uses a deterministic graph
optimiser (no language model in the loop), the range mock of XiiD, and simulated
approver devices whenever ``RangeApprovalBoard`` is used.
"""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from s3m_core.defense.audit.merkle_log import AuditEntry, MerkleAuditLog

from src.cortex.approvals.crypto_util import (
    canonical_approval_payload,
    generate_device_keypair,
    new_nonce,
    sign_payload,
)
from src.cortex.approvals.service import ApprovalService
from src.cortex.architect import (
    ArchitectureOption,
    ProposedChange,
    apply_changes,
    asset_exposure,
    propose_options,
    recommended,
)
from src.cortex.cybertwin import CyberTwinGraph, build_twin, prioritized_findings
from src.cortex.xiid_broker import XiidMCPBroker
from src.cortex.xiid_write_envelope import WriteEnvelope, arguments_digest

RISK_TOLERANCE = 1e-6
ENVELOPE_TTL_SECONDS = 900


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------------------
# Range-only approver devices
# --------------------------------------------------------------------------------------
@dataclass
class SimulatedApproverDevice:
    """RANGE ONLY: stands in for a human's registered approval device."""

    device_id: str
    label: str
    private_key: bytes
    public_key: bytes

    @classmethod
    def create(cls, device_id: str, label: str) -> "SimulatedApproverDevice":
        priv, pub = generate_device_keypair()
        return cls(device_id=device_id, label=label, private_key=priv, public_key=pub)

    def sign(self, change_id: str, envelope_id: str, decision: str) -> Dict[str, str]:
        ts = _now()
        nonce = new_nonce()
        payload = canonical_approval_payload(
            change_id=change_id, envelope_id=envelope_id, decision=decision, timestamp=ts, nonce=nonce
        )
        return {"timestamp": ts, "nonce": nonce, "signature_b64": sign_payload(self.private_key, payload)}


class RangeApprovalBoard:
    """RANGE ONLY: registers simulated devices through the real two-admin flow and votes.

    ``policy(change_payload) -> "APPROVE" | "DENY"`` lets scenarios model human refusals.
    """

    SIMULATED = True

    def __init__(
        self,
        service: ApprovalService,
        *,
        n_devices: int = 3,
        policy: Optional[Callable[[Mapping[str, Any]], str]] = None,
    ) -> None:
        self.service = service
        self.policy = policy or (lambda _payload: "APPROVE")
        self.devices: List[SimulatedApproverDevice] = []
        for admin in ("range-admin-1", "range-admin-2"):
            service.register_admin_identity(admin)
        for i in range(1, n_devices + 1):
            dev = SimulatedApproverDevice.create(f"range-approver-{i}", f"Simulated approver {i}")
            reg = service.start_device_registration(
                device_id=dev.device_id,
                public_key_b64=base64.b64encode(dev.public_key).decode("ascii"),
                approver_label=dev.label,
                duress_pin=uuid.uuid4().hex,
            )
            service.admin_approve_registration(registration_id=reg["registration_id"], admin_id="range-admin-1")
            service.admin_approve_registration(registration_id=reg["registration_id"], admin_id="range-admin-2")
            self.devices.append(dev)

    def vote(self, change_id: str, envelope_id: str, required: int, payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
        votes = []
        decision = self.policy(payload)
        for dev in self.devices[: max(required, 1)]:
            signed = dev.sign(change_id, envelope_id, decision)
            res = self.service.submit_approval(
                change_id,
                device_id=dev.device_id,
                session_id=f"device-session-{dev.device_id}",
                envelope_id=envelope_id,
                decision=decision,
                **signed,
            )
            votes.append({"device_id": dev.device_id, "decision": res["recorded_decision"], "simulated": True})
        return votes


# --------------------------------------------------------------------------------------
# Cycle
# --------------------------------------------------------------------------------------
@dataclass
class CycleReport:
    case_id: str
    started_at: str
    labels: Dict[str, str]
    stages: List[Dict[str, Any]] = field(default_factory=list)
    discovery: Dict[str, Any] = field(default_factory=dict)
    twin: Dict[str, Any] = field(default_factory=dict)
    analysis: Dict[str, Any] = field(default_factory=dict)
    options: List[Dict[str, Any]] = field(default_factory=list)
    recommended_option: Optional[str] = None
    changes: List[Dict[str, Any]] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)
    rollback: Dict[str, Any] = field(default_factory=dict)
    escalations: List[Dict[str, Any]] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)
    outcome: str = "pending"
    finished_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class DefenseCycle:
    def __init__(
        self,
        *,
        broker: XiidMCPBroker,
        audit_log: MerkleAuditLog,
        mission: Mapping[str, Any],
        approval_service: ApprovalService,
        approval_board: RangeApprovalBoard,
        envelope_signing_key: bytes,
        session_id: str,
        operator_id: str = "range-operator",
        proposer_device_id: str = "cortex-proposer",
        budget: float = 8.0,
        xiid_label: str = "mock XiiD MCP server (range, streamable HTTP)",
        expire_inverse: Optional[str] = None,
        approval_sink: Optional[Callable[[str, Mapping[str, Any], List[str]], None]] = None,
        exposure_target: Optional[float] = None,
    ) -> None:
        self.broker = broker
        self.audit_log = audit_log
        self.mission = mission
        self.approvals = approval_service
        self.board = approval_board
        self.key = envelope_signing_key
        self.session_id = session_id
        self.operator_id = operator_id
        self.proposer_device_id = proposer_device_id
        self.budget = budget
        self.xiid_label = xiid_label
        self.expire_inverse = expire_inverse
        # Called with (logical action, arguments, approval ids) once human approval is
        # satisfied, so an independent Approval Authority can mint a server-verifiable token.
        self.approval_sink = approval_sink
        # When set, the architect adds the BreachPath exact option and recommends the
        # cheapest plan reaching the exposure target (proven achievable).
        self.exposure_target = exposure_target

    # ---- evidence ----------------------------------------------------------------
    def _stage(self, report: CycleReport, stage: str, status: str, **details: Any) -> None:
        rec = {"stage": stage, "status": status, "at": _now(), **details}
        report.stages.append(rec)
        self.audit_log.append(
            AuditEntry(
                timestamp=datetime.now(timezone.utc),
                session_id=self.session_id,
                event_type=f"cortex.cycle.{stage}",
                source_layer="cortex.defense_cycle",
                severity="warning" if status in {"failed", "escalated", "rolled_back"} else "info",
                details={"case_id": report.case_id, "status": status, **details},
                previous_hash="",
            )
        )

    # ---- XiiD reads --------------------------------------------------------------
    async def _observe(self) -> Dict[str, Any]:
        routes = (await self.broker.invoke("list_routes")).result.get("routes", [])
        findings = (await self.broker.invoke("list_vuln_findings")).result.get("findings", [])
        stlinks = (await self.broker.invoke("list_stlinks")).result.get("stlinks", [])
        health = (await self.broker.invoke("telemetry_health")).result
        return {"routes": routes, "findings": findings, "stlinks": stlinks, "health": health}

    @staticmethod
    def _route(observed: Mapping[str, Any], route_id: str) -> Optional[Dict[str, Any]]:
        return next((dict(r) for r in observed["routes"] if r.get("id") == route_id), None)

    @staticmethod
    def _postcondition_ok(route: Optional[Mapping[str, Any]], expected: Mapping[str, Any]) -> bool:
        if route is None:
            return False
        return all(route.get(k) == v for k, v in expected.items() if k != "route_id")

    # ---- authorisation -----------------------------------------------------------
    def _authorize(self, case_id: str, change: ProposedChange) -> Dict[str, Any]:
        binding = self.broker_tool_class(change.xiid_action)
        change_class = "D" if not change.reversible else binding
        envelope_id = f"env-{case_id}-{change.change_id}"
        diff = {
            "tool_action": change.xiid_action,
            "arguments": change.arguments,
            "arguments_sha256": arguments_digest(change.arguments),
            "rollback": (
                {"action": change.rollback_action, "arguments": change.rollback_arguments}
                if change.reversible
                else "NONE - irreversible with current XiiD tool contract"
            ),
        }
        req = self.approvals.request_change_approval(
            f"{case_id}:{change.change_id}",
            {
                "change_class": change_class,
                "envelope_id": envelope_id,
                "diff": str(diff),
                "interpreter_context": change.rationale,
                "risk_before": {"system_risk": change.risk_before},
                "risk_after": {"system_risk": change.risk_after},
                "blast_radius": {"disrupted_sessions_30d": change.disrupted_sessions_30d},
                "rollback_steps": [str(diff["rollback"])],
                "proposer_device_id": self.proposer_device_id,
                "proposer_session_id": self.session_id,
            },
        )
        votes = self.board.vote(
            f"{case_id}:{change.change_id}",
            envelope_id,
            int(req["required_approval_count"]),
            {"change": change.to_dict(), "change_class": change_class},
        )
        satisfied = self.approvals.gate_satisfied(f"{case_id}:{change.change_id}")
        out: Dict[str, Any] = {
            "change_class": change_class,
            "required_approvals": req["required_approval_count"],
            "votes": votes,
            "gate_satisfied": satisfied,
            "envelope_id": envelope_id,
        }
        if satisfied and self.approval_sink is not None:
            ids = [f"{envelope_id}:{v['device_id']}" for v in votes if v["decision"] == "APPROVE"]
            self.approval_sink(change.xiid_action, change.arguments, ids)
            if change.reversible and change.rollback_action:
                self.approval_sink(str(change.rollback_action), dict(change.rollback_arguments or {}), ids)
        if satisfied:
            out["write_envelope"] = WriteEnvelope.issue(
                operator_id=self.operator_id,
                session_id=self.session_id,
                action=change.xiid_action,
                signing_key=self.key,
                arguments=change.arguments,
                ttl_seconds=ENVELOPE_TTL_SECONDS,
            )
            if change.reversible and change.rollback_action:
                out["rollback_envelope"] = WriteEnvelope.issue(
                    operator_id=self.operator_id,
                    session_id=self.session_id,
                    action=change.rollback_action,
                    signing_key=self.key,
                    arguments=change.rollback_arguments,
                    ttl_seconds=ENVELOPE_TTL_SECONDS,
                )
        return out

    def broker_tool_class(self, action: str) -> str:
        return self.broker._tool_map.resolve(action).tool_class  # noqa: SLF001 - read-only lookup

    # ---- main loop ---------------------------------------------------------------
    async def run(self, case_id: Optional[str] = None) -> CycleReport:
        case_id = case_id or f"case-{uuid.uuid4().hex[:8]}"
        report = CycleReport(
            case_id=case_id,
            started_at=_now(),
            labels={
                "reasoning": "deterministic graph optimiser (MRC); no language model in this loop",
                "xiid": self.xiid_label,
                "approvers": "SIMULATED devices (range only)" if getattr(self.board, "SIMULATED", False) else "registered devices",
                "data": "synthetic enterprise; no real hosts, users or CVEs",
            },
        )
        t0 = time.perf_counter()

        # 1. Discover (class A reads through the broker; manifest pinned first)
        digest = await self.broker.connect_and_pin_manifest()
        observed = await self._observe()
        report.discovery = {
            "manifest_digest": digest,
            "routes": len(observed["routes"]),
            "findings": len(observed["findings"]),
            "stlinks": len(observed["stlinks"]),
            "health": observed["health"],
        }
        self._stage(report, "discover", "ok", **{k: v for k, v in report.discovery.items() if k != "health"})

        # 2. Twin + analysis
        twin = build_twin(observed["routes"], observed["findings"], self.mission)
        report.twin = twin.summary()
        report.analysis = {
            "top_attack_paths": [{**p, "probability": round(p["probability"], 6)} for p in twin.top_attack_paths(8)],
            "asset_exposure": asset_exposure(twin),
            "unnecessary_routes": [
                {"route_id": m.route_id, "source": m.source, "target": m.target, "service": m.service}
                for m in twin.unnecessary_routes()
            ],
            "prioritized_findings": prioritized_findings(twin, observed["findings"])[:8],
        }
        self._stage(report, "analyze", "ok", system_risk=report.twin["system_risk"])

        # 3. Architect: alternatives, simulated on the twin
        options = propose_options(twin, budget=self.budget, expire_inverse=self.expire_inverse,
                                  exact_threshold=self.exposure_target)
        report.options = [o.to_dict() for o in options]
        choice = recommended(options)
        if choice is None:
            report.outcome = "no_action"
            self._stage(report, "architect", "no_viable_option")
            return self._finish(report, t0)
        report.recommended_option = choice.option_id
        self._stage(report, "architect", "ok", recommended=choice.option_id, options=len(options))

        # 4. Authorise each change (out-of-band approvals + bound envelopes)
        ordered = sorted(choice.changes, key=lambda c: (not c.reversible, c.change_id))
        auths: Dict[str, Dict[str, Any]] = {}
        approved: List[ProposedChange] = []
        for ch in ordered:
            try:
                auth = self._authorize(case_id, ch)
            except Exception as exc:  # kill switch engaged, approval service refusal
                auth = {"gate_satisfied": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            auths[ch.change_id] = auth
            if auth["gate_satisfied"]:
                ch.state = "approved"
                approved.append(ch)
            else:
                ch.state = "denied"
        self._stage(
            report,
            "authorize",
            "ok" if approved else "denied",
            approved=[c.change_id for c in approved],
            denied=[c.change_id for c in ordered if c.state == "denied"],
        )
        if not approved:
            report.outcome = "no_action"
            report.changes = [
                {**c.to_dict(), "authorization": {k: v for k, v in auths.get(c.change_id, {}).items()
                                                   if not hasattr(v, "to_dict")}}
                for c in ordered
            ]
            report.audit = {"merkle_chain_intact": self.broker.verify_evidence_chain()}
            self._stage(report, "verify", "no_action", reason="no change approved")
            return self._finish(report, t0)
        predicted = apply_changes(twin, approved)
        predicted_risk = predicted.system_risk()

        # 5. Execute + per-step verification
        executed: List[ProposedChange] = []
        failure: Optional[Dict[str, Any]] = None
        for ch in approved:
            auth = auths[ch.change_id]
            try:
                self.approvals.policy_gate.assert_writes_allowed()
                res = await self.broker.invoke(
                    ch.xiid_action,
                    ch.arguments,
                    envelope=auth["write_envelope"],
                    idempotency_key=f"{case_id}:{ch.change_id}",
                )
                ch.state = "executed"
                executed.append(ch)
                after = self._route(await self._observe(), ch.route_id)
                if self._postcondition_ok(after, ch.expected_postcondition):
                    ch.state = "verified"
                else:
                    ch.state = "failed"
                    failure = {"change_id": ch.change_id, "reason": "postcondition_mismatch",
                               "expected": ch.expected_postcondition, "observed": after,
                               "tool_acknowledged": bool(res.result)}
            except Exception as exc:  # tool error, gate, broker refusal
                ch.state = "failed"
                failure = {"change_id": ch.change_id, "reason": type(exc).__name__, "detail": str(exc)[:200]}
            self._stage(report, "execute", ch.state, change_id=ch.change_id, xiid_action=ch.xiid_action)
            if failure:
                break

        # 6. Whole-twin verification from observed state
        final_obs = await self._observe()
        observed_twin = build_twin(final_obs["routes"], final_obs["findings"], self.mission)
        report.verification = {
            "predicted_system_risk": round(predicted_risk, 6),
            "observed_system_risk": round(observed_twin.system_risk(), 6),
            "baseline_system_risk": report.twin["system_risk"],
            "observed_asset_exposure": asset_exposure(observed_twin),
            "observed_broken_flows": observed_twin.broken_flows(),
            "matches_prediction": abs(predicted_risk - observed_twin.system_risk()) <= RISK_TOLERANCE,
            "failure": failure,
        }

        # 7. Rollback + escalation on failure
        if failure:
            for ch in approved:
                if ch.state == "approved":
                    ch.state = "cancelled"  # approved but never dispatched: plan halted
            report.rollback = await self._rollback(case_id, executed, auths, report)
            for ch in executed:
                if not ch.reversible and ch.state in {"verified", "executed"}:
                    report.escalations.append({"change_id": ch.change_id, "reason": "irreversible change applied before failure"})
            report.escalations.append({"change_id": failure["change_id"], "reason": failure["reason"],
                                       "action": "operator review required; plan halted"})
            report.outcome = "rolled_back" if report.rollback.get("restored") else "escalated"
            self._stage(report, "verify", report.outcome, failure=failure["change_id"])
        else:
            ok = report.verification["matches_prediction"] and not report.verification["observed_broken_flows"]
            report.outcome = "verified" if ok else "escalated"
            if not ok:
                report.escalations.append({"reason": "observed state diverges from prediction"})
            self._stage(report, "verify", report.outcome)

        report.changes = [
            {**c.to_dict(), "authorization": {k: (v.to_dict() if hasattr(v, "to_dict") else v)
                                               for k, v in auths.get(c.change_id, {}).items()}}
            for c in ordered
        ]
        report.audit = {
            "merkle_chain_intact": self.broker.verify_evidence_chain(),
            "audit_log": str(self.audit_log.log_path),
        }
        return self._finish(report, t0)

    async def _rollback(
        self,
        case_id: str,
        executed: Sequence[ProposedChange],
        auths: Mapping[str, Mapping[str, Any]],
        report: CycleReport,
    ) -> Dict[str, Any]:
        steps = []
        for ch in reversed(executed):
            if not ch.reversible:
                route = self._route(await self._observe(), ch.route_id)
                applied = route is not None and route.get("status") == "expired"
                steps.append({"change_id": ch.change_id, "status": "not_reversible" if applied else "not_applied"})
                continue
            env = auths[ch.change_id].get("rollback_envelope")
            try:
                await self.broker.invoke(
                    str(ch.rollback_action),
                    ch.rollback_arguments,
                    envelope=env,
                    idempotency_key=f"{case_id}:{ch.change_id}:rollback",
                )
                route = self._route(await self._observe(), ch.route_id)
                # Effective policy restored: enforced, and not narrower than its own prefix.
                restored = (
                    route is not None
                    and route.get("status") != "expired"
                    and route.get("narrow_to") in (None, route.get("prefix"))
                )
                ch.state = "rolled_back" if restored else "rollback_failed"
                steps.append({"change_id": ch.change_id, "status": ch.state})
            except Exception as exc:
                ch.state = "rollback_failed"
                steps.append({"change_id": ch.change_id, "status": "rollback_failed", "detail": str(exc)[:200]})
        obs = await self._observe()
        twin_after = build_twin(obs["routes"], obs["findings"], self.mission)
        # Restored only if every applied reversible change was undone and nothing
        # irreversible had actually been applied.
        restored = all(s["status"] in {"rolled_back", "not_applied"} for s in steps)
        result = {
            "performed": bool(steps),
            "steps": steps,
            "restored": restored,
            "system_risk_after_rollback": round(twin_after.system_risk(), 6),
            "broken_flows_after_rollback": twin_after.broken_flows(),
        }
        self._stage(report, "rollback", "rolled_back" if restored else "escalated", steps=len(steps))
        return result

    def _finish(self, report: CycleReport, t0: float) -> CycleReport:
        report.finished_at = _now()
        report.audit.setdefault("duration_seconds", round(time.perf_counter() - t0, 3))
        report.audit["duration_seconds"] = round(time.perf_counter() - t0, 3)
        return report


def option_table(options: Sequence[ArchitectureOption | Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for o in options:
        d = o.to_dict() if hasattr(o, "to_dict") else dict(o)
        rows.append(
            {
                "option": d["option_id"],
                "label": d["label"],
                "risk": f"{d['initial_risk']:.3f} -> {d['final_risk']:.3f}",
                "changes": len(d["changes"]),
                "irreversible": d["irreversible_changes"],
                "disrupted_sessions_30d": d["disrupted_sessions_30d"],
                "flows_ok": d["required_flows_ok"],
                "recommended": d["recommended"],
            }
        )
    return rows


__all__ = [
    "CycleReport",
    "DefenseCycle",
    "RangeApprovalBoard",
    "SimulatedApproverDevice",
    "option_table",
    "CyberTwinGraph",
]
