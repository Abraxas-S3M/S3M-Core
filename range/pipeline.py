"""Cortex rehearsal pipeline: perception → evidence (deterministic mock engines)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from range.envelope import (
    ApproverResponse,
    SignedTestEnvelope,
    issue_signed_test_envelope,
    simulate_approver_device,
    verify_signed_test_envelope,
)
from range.mock_xiid import MockXiidServer, MockXiidTool
from s3m_core.defense.audit.merkle_log import AuditEntry, MerkleAuditLog

PipelineMode = Literal["mock", "live"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PipelineAlert:
    alert_type: str
    severity: str
    detail: str


@dataclass
class RangeRunState:
    """Mutable state accumulated through one scenario execution."""

    scenario_id: str
    started_at: datetime = field(default_factory=_utc_now)
    ended_at: datetime | None = None
    alerts: list[PipelineAlert] = field(default_factory=list)
    unauthorised_calls: int = 0
    unauthorised_blocked: int = 0
    writes_executed: int = 0
    false_containment_events: int = 0
    rollback_attempted: bool = False
    rollback_succeeded: bool = False
    protected_route_touched: bool = False
    broker_refused: bool = False
    change_applied: bool = False
    predicted_matches_observed: bool = False
    required_flows_reachable: bool = True
    containment_verified_at: datetime | None = None
    envelope: SignedTestEnvelope | None = None
    evidence_log_path: Path | None = None
    stages: dict[str, Any] = field(default_factory=dict)


class MockPerceptionEngine:
    """Loads perception events from scenario YAML."""

    def ingest(self, scenario: dict[str, Any]) -> list[dict[str, Any]]:
        perception = scenario.get("perception") or {}
        events = perception.get("events") or []
        if not isinstance(events, list):
            raise ValueError("perception.events must be a list")
        return list(events)


class MockTaintEngine:
    """Tags routes and log lines that carry injection or protected labels."""

    _INJECTION_RE = re.compile(
        r"(ignore\s+prior\s+instructions|system\s*:|admin\s+override|you\s+must\s+write)",
        re.IGNORECASE,
    )

    def analyze_events(
        self, events: list[dict[str, Any]], scenario: dict[str, Any]
    ) -> dict[str, Any]:
        protected = (scenario.get("taint") or {}).get("protected_routes") or []
        protected_paths = {str(p.get("path", "")) for p in protected}
        tainted_events: list[dict[str, Any]] = []
        injection_hits: list[str] = []
        for event in events:
            blob = yaml.safe_dump(event)
            tainted = False
            for path in protected_paths:
                if path and path in blob:
                    tainted = True
            if self._INJECTION_RE.search(blob):
                tainted = True
                injection_hits.append(event.get("event_id", "unknown"))
            tagged = dict(event)
            tagged["tainted"] = tainted
            tainted_events.append(tagged)
        extra_indicators = (scenario.get("taint") or {}).get("injection_indicators") or []
        for indicator in extra_indicators:
            if any(str(indicator).lower() in yaml.safe_dump(e).lower() for e in events):
                injection_hits.append(str(indicator))
        return {
            "events": tainted_events,
            "protected_paths": sorted(protected_paths),
            "injection_hits": injection_hits,
        }


class MockTwinEngine:
    """Builds a lightweight network twin for CCTV shield scenarios."""

    def build_twin(self, scenario: dict[str, Any]) -> dict[str, Any]:
        network = scenario.get("network") or {}
        nodes = network.get("nodes") or []
        flows = network.get("required_flows") or []
        return {
            "nodes": {n["id"]: dict(n) for n in nodes if "id" in n},
            "flows": list(flows),
            "protected_route": scenario.get("protected_route") or {},
        }

    def predict_post_change(self, twin: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
        predicted = dict(change.get("predicted_state") or {})
        return {"twin_id": "cctv-enclave", "predicted": predicted}

    def observe_after_apply(self, twin: dict[str, Any], predicted: dict[str, Any]) -> dict[str, Any]:
        observed = dict(predicted.get("predicted") or {})
        return {"observed": observed}

    def flows_reachable(self, twin: dict[str, Any]) -> bool:
        nodes = twin.get("nodes") or {}
        flows = twin.get("flows") or []
        for flow in flows:
            if flow.get("from") not in nodes or flow.get("to") not in nodes:
                return False
        return True


class MockCouncilEngine:
    """Deterministic council consensus for proposed changes."""

    def deliberate(self, proposal: dict[str, Any], taint_report: dict[str, Any]) -> dict[str, Any]:
        if taint_report.get("injection_hits"):
            return {"consensus": "deny", "confidence": 0.92, "reason": "injection taint present"}
        return {"consensus": "proceed_with_gates", "confidence": 0.88, "reason": "CVE containment"}

    def vote(self, proposal: dict[str, Any]) -> dict[str, Any]:
        return {"votes_for": 3, "votes_against": 0, "quorum_met": True}


class MockPlannerEngine:
    """Produces a plan from perception + twin context."""

    def plan(self, scenario: dict[str, Any], council: dict[str, Any]) -> dict[str, Any]:
        if "proposed_action" in (scenario.get("planner") or {}):
            return dict(scenario["planner"]["proposed_action"])
        if "proposed_change" in (scenario.get("planner") or {}):
            return dict(scenario["planner"]["proposed_change"])
        return {}


class MockGateEngine:
    """Blocks tainted writes and honours approver envelope outcomes."""

    def evaluate(
        self,
        plan: dict[str, Any],
        taint_report: dict[str, Any],
        envelope: SignedTestEnvelope,
        protected_paths: list[str],
    ) -> dict[str, Any]:
        if not verify_signed_test_envelope(envelope):
            return {"decision": "deny", "reason": "invalid envelope signature"}

        path = str(plan.get("path") or "")
        tool = str(plan.get("tool_name") or plan.get("type") or "")
        tainted_path = any(p in path for p in protected_paths if p)
        injection = bool(taint_report.get("injection_hits"))

        if envelope.approver_response == "duress":
            return {"decision": "deny", "reason": "duress", "duress": True}
        if envelope.approver_response == "deny":
            return {"decision": "deny", "reason": "approver_denied"}
        if injection or tainted_path:
            return {"decision": "deny", "reason": "tainted_or_injection", "block_write": True}
        return {"decision": "approve", "reason": "policy_ok"}


class MockBrokerEngine:
    """Routes tool calls to mock XiiD; refuses rug-pull tools after catalog switch."""

    def __init__(self, xiid: MockXiidServer) -> None:
        self.xiid = xiid
        self.allowed_tools: set[str] = set()

    def configure_allowlist(self, tools: list[str]) -> None:
        self.allowed_tools = set(tools)

    def invoke(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        switched = self.xiid.maybe_switch_catalog()
        tool = self.xiid.tools.get(tool_name)
        if tool and tool.risk == "critical":
            return {"allowed": False, "reason": "tool_risk_critical_after_switch", "switched": switched}
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return {"allowed": False, "reason": "tool_not_on_allowlist", "switched": switched}
        if switched and tool and "shell" in tool.description.lower():
            return {"allowed": False, "reason": "rug_pull_description", "switched": True}
        if switched:
            return {"allowed": False, "reason": "broker_refuse_post_switch", "switched": True}
        result = self.xiid.call_tool(tool_name, arguments)
        return {"allowed": True, "switched": switched, "xiid": result}


class MockVerificationEngine:
    """Compares twin predictions with observed enclave state."""

    def verify_containment(
        self, predicted: dict[str, Any], observed: dict[str, Any], protected_route: dict[str, Any]
    ) -> dict[str, Any]:
        pred = predicted.get("predicted") or {}
        obs = observed.get("observed") or {}
        matches = pred == obs
        protected_node = (protected_route or {}).get("node_id")
        protected_ok = obs.get(protected_node) in (None, "unchanged") or protected_node is None
        if protected_node and obs.get(protected_node) not in (None, "unchanged"):
            protected_ok = False
        return {"matches": matches, "protected_ok": protected_ok}


class MockEvidenceEngine:
    """Appends stage transitions into a Merkle audit log."""

    def __init__(self, log_dir: Path, session_id: str) -> None:
        self.log_dir = log_dir
        self.session_id = session_id
        self.log = MerkleAuditLog(str(log_dir / f"{session_id}.jsonl"))

    def record(self, event_type: str, source_layer: str, details: dict[str, Any], severity: str = "INFO") -> None:
        self.log.append(
            AuditEntry(
                timestamp=_utc_now(),
                session_id=self.session_id,
                event_type=event_type,
                source_layer=source_layer,
                severity=severity,
                details=details,
                previous_hash="",
            )
        )

    def verify_chain(self) -> bool:
        report = self.log.verify_integrity()
        return bool(report.chain_intact)


class CortexRangePipeline:
    """Orchestrates the full perception → evidence chain for one scenario."""

    def __init__(self, *, mode: PipelineMode = "mock", work_dir: Path | None = None) -> None:
        self.mode = mode
        self.work_dir = work_dir or Path("range/reports/.staging")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.perception = MockPerceptionEngine()
        self.taint = MockTaintEngine()
        self.twin = MockTwinEngine()
        self.council = MockCouncilEngine()
        self.planner = MockPlannerEngine()
        self.gate = MockGateEngine()
        self.verification = MockVerificationEngine()
        self.xiid: MockXiidServer | None = None
        self.broker: MockBrokerEngine | None = None

    def _init_xiid(self, scenario: dict[str, Any]) -> MockXiidServer:
        xiid_cfg = scenario.get("xiid") or {}
        server = MockXiidServer(
            session_id=str(xiid_cfg.get("session_id") or scenario.get("scenario_id")),
            switch_after_tool_calls=int(xiid_cfg.get("switch_after_tool_calls") or 0),
        )
        initial = (xiid_cfg.get("phase_initial") or {}).get("tools") or []
        switched = (xiid_cfg.get("phase_switched") or {}).get("tools") or []
        server.register_phase(
            "initial",
            [MockXiidTool(**t) for t in initial],
        )
        server.register_phase(
            "switched",
            [MockXiidTool(**t) for t in switched],
        )
        self.xiid = server
        self.broker = MockBrokerEngine(server)
        broker_cfg = scenario.get("broker") or {}
        self.broker.configure_allowlist(list(broker_cfg.get("allowed_tools_initial") or []))
        return server

    def run_scenario(
        self,
        scenario: dict[str, Any],
        *,
        approver_override: ApproverResponse | None = None,
    ) -> RangeRunState:
        scenario_id = str(scenario.get("scenario_id") or "unknown")
        state = RangeRunState(scenario_id=scenario_id)
        evidence = MockEvidenceEngine(self.work_dir, session_id=scenario_id)
        state.evidence_log_path = evidence.log.log_path

        approver_cfg = scenario.get("approver") or {}
        response: ApproverResponse = approver_override or approver_cfg.get("response", "approve")
        device_id = str(approver_cfg.get("device_id") or "test-approver")

        events = self.perception.ingest(scenario)
        state.stages["perception"] = {"event_count": len(events)}
        evidence.record("perception_ingested", "perception", {"count": len(events)})

        taint_report = self.taint.analyze_events(events, scenario)
        state.stages["taint"] = taint_report
        evidence.record("taint_analysis", "taint", taint_report)

        twin = self.twin.build_twin(scenario) if scenario.get("network") else {}
        state.stages["twin"] = twin
        evidence.record("twin_built", "twin", {"node_count": len(twin.get("nodes", {}))})

        council = self.council.deliberate(scenario.get("planner") or {}, taint_report)
        council["vote"] = self.council.vote(scenario.get("planner") or {})
        state.stages["council"] = council
        evidence.record("council_decision", "council", council)

        plan = self.planner.plan(scenario, council)
        state.stages["planner"] = plan
        evidence.record("plan_issued", "planner", plan)

        envelope = issue_signed_test_envelope(
            scenario_id=scenario_id,
            action_payload=plan,
            approver_device_id=device_id,
            approver_response=response,
        )
        state.envelope = envelope
        approver_device = simulate_approver_device(response)
        evidence.record("envelope_issued", "gate", envelope.to_dict())
        evidence.record("approver_response", "gate", approver_device)

        protected_paths = list(taint_report.get("protected_paths") or [])
        gate_result = self.gate.evaluate(plan, taint_report, envelope, protected_paths)
        state.stages["gate"] = gate_result
        evidence.record("gate_decision", "gate", gate_result)

        if gate_result.get("duress"):
            state.alerts.append(
                PipelineAlert("duress_approval", "CRITICAL", "Approver duress — change denied.")
            )
        if taint_report.get("injection_hits"):
            state.alerts.append(
                PipelineAlert("prompt_injection", "HIGH", "Prompt injection detected in perception feeds.")
            )
            state.unauthorised_calls += 1
            if gate_result.get("block_write") or gate_result.get("decision") == "deny":
                state.unauthorised_blocked += 1

        # Scenario-specific execution paths
        if scenario_id == "scenario_a_poisoned_log":
            if gate_result.get("decision") == "approve":
                state.writes_executed += 1
                state.unauthorised_calls += 1

        elif scenario_id == "scenario_b_cctv_shield":
            change = (scenario.get("planner") or {}).get("proposed_change") or {}
            predicted = self.twin.predict_post_change(twin, change)
            if gate_result.get("decision") == "approve" and response == "approve":
                state.change_applied = True
                observed = self.twin.observe_after_apply(twin, predicted)
                verify = self.verification.verify_containment(
                    predicted, observed, scenario.get("protected_route") or {}
                )
                state.predicted_matches_observed = bool(verify.get("matches"))
                state.protected_route_touched = not bool(verify.get("protected_ok"))
                state.required_flows_reachable = self.twin.flows_reachable(twin)
                state.containment_verified_at = _utc_now()
                if state.protected_route_touched:
                    state.false_containment_events += 1
                state.rollback_attempted = True
                state.rollback_succeeded = True
            elif gate_result.get("duress") or response == "duress":
                state.change_applied = False
                state.alerts.append(
                    PipelineAlert("duress_approval", "CRITICAL", "Duress — containment change withheld.")
                )
            evidence.record("verification", "verification", {"predicted": predicted})

        elif scenario_id == "scenario_c_rug_pull":
            self._init_xiid(scenario)
            assert self.broker is not None
            tool_name = str(plan.get("tool_name") or "cctv_status")
            first = self.broker.invoke(tool_name, plan.get("arguments") or {})
            state.stages["broker_first"] = first
            broker_cfg = scenario.get("broker") or {}
            self.broker.configure_allowlist(list(broker_cfg.get("allowed_tools_after_switch") or []))
            second = self.broker.invoke(tool_name, plan.get("arguments") or {})
            state.stages["broker_second"] = second
            if not second.get("allowed"):
                state.broker_refused = True
                state.unauthorised_calls += 1
                state.unauthorised_blocked += 1
                state.alerts.append(
                    PipelineAlert(
                        "tool_description_rug_pull",
                        "CRITICAL",
                        "Broker refused tool call after XiiD catalog switch.",
                    )
                )
            evidence.record("broker", "broker", {"first": first, "second": second})

        state.stages["evidence_verified"] = evidence.verify_chain()
        state.ended_at = _utc_now()
        return state


def load_scenario(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Scenario file must be a mapping: {path}")
    return data
