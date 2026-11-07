"""Scenario B — full Cortex pipeline fixture for audit/report integration tests.

Stages: council → planner → gate → broker → verification, with one case_id binding
trace, Merkle audit, and the explainability bundle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dataclasses import asdict

from src.cortex.ace import ReliabilityStore
from src.cortex.audit import CortexAuditRecorder
from src.cortex.broker import CortexBroker
from src.cortex.changes import NetworkChange
from src.cortex.council import CyberTaskType, EngineCouncil, RoleEngine
from src.cortex.mrc import MRCSnapshot, assess_mrc
from src.cortex.pccp_invariants import evaluate_pccp
from src.cortex.pipeline_planner import CortexPlan, build_plan
from src.cortex.policy_gate import Approval, MissionEnvelope, PolicyGate, PolicyGateConfig
from src.cortex.tracing import CortexTracer, verify_trace_matches_case
from src.cortex.verification import VerificationResult, verify_and_rollback
from src.cortex.xiid import XiiDRecorder, XiiDRecordRef


@dataclass
class ScenarioBInputs:
    case_id: str
    trusted_context: str
    evidence_ids: List[str]
    case_evidence: Dict[str, str]
    untrusted_fields: Dict[str, str]
    input_trust: Dict[str, str]
    approvals: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ScenarioBResult:
    case_id: str
    inputs: ScenarioBInputs
    council_output: str
    plan: CortexPlan
    gate_allowed: bool
    gate_reason: str
    broker_applied: bool
    mrc_before: MRCSnapshot
    mrc_after: MRCSnapshot
    verification: VerificationResult
    xiid_ref: Optional[XiiDRecordRef]
    audit_log_path: Path
    trace_export_path: Path
    workspace: Path


def run_scenario_b(
    workspace: Path,
    *,
    council_factory: Optional[Callable[[Path], EngineCouncil]] = None,
) -> ScenarioBResult:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    case_id = str(uuid.uuid4())

    # Deliberate decoy secret in untrusted telemetry — must not reach traces/reports.
    poison_log = "auth failure bearer_token=supersecretBearerABCDEF0123456789"
    inputs = ScenarioBInputs(
        case_id=case_id,
        trusted_context="Scenario B — lateral movement investigation",
        evidence_ids=["EV-B1", "EV-B2"],
        case_evidence={
            "EV-B1": "src=10.1.2.3 dst=203.0.113.44 action=deny",
            "EV-B2": "user svc-backup auth_fail count=12",
        },
        untrusted_fields={"raw_log": poison_log, "alert_title": "Possible lateral movement"},
        input_trust={
            "EV-B1": "sensor:ids:high",
            "EV-B2": "sensor:auth:medium",
            "raw_log": "untrusted:siem",
            "alert_title": "untrusted:edm",
        },
        approvals=[
            {
                "approver": "operator-7",
                "proposer": "orchestrator",
                "channel": "out_of_band_device",
            },
            {
                "approver": "operator-7",
                "proposer": "orchestrator",
                "channel": "out_of_band_device",
                "duress": True,
                "outcome": "coerced",
            },
        ],
    )

    audit_path = workspace / "audit.jsonl"
    trace_dir = workspace / "traces"
    recorder = CortexAuditRecorder(log_path=audit_path)
    tracer = CortexTracer(case_id=case_id, output_dir=trace_dir)
    xiid = XiiDRecorder()

    recorder.record_stage(
        case_id=case_id,
        stage="inputs",
        event_type="cortex.case_opened",
        details={"input_trust": inputs.input_trust, "evidence_ids": inputs.evidence_ids},
    )

    mrc_before = assess_mrc(evidence_count=len(inputs.evidence_ids), ace_dropped=0, gate_allowed=True)

    if council_factory is None:
        council_factory = _default_council_factory

    with tracer.span("council", stage="council", attributes={"task": "attack_path"}):
        council = council_factory(workspace)
        council_result = council.run(
            CyberTaskType.ATTACK_PATH,
            evidence_ids=inputs.evidence_ids,
            case_evidence=inputs.case_evidence,
            trusted_context=inputs.trusted_context,
            untrusted_fields=inputs.untrusted_fields,
        )
        council_output = council_result.output
        ace = council_result.ace
        recorder.record_stage(
            case_id=case_id,
            stage="council",
            event_type="cortex.council_complete",
            details={
                "task_type": council_result.task_type.value,
                "route": {
                    "role": council_result.route.role,
                    "engine_id": council_result.route.engine_id,
                    "uses_ace": council_result.route.uses_ace,
                },
                "ace": ace.to_dict() if ace is not None else None,
                "output_preview": council_output[:240],
            },
        )

    engine_versions = {
        council_result.route.engine_id: "fixture-1.0.0",
        "challenger": "fixture-1.0.0",
    }

    with tracer.span("planner", stage="planner"):
        plan = build_plan(
            case_id=case_id,
            ace=ace,
            council_output=council_output,
            engine_versions=engine_versions,
        )
        recorder.record_stage(
            case_id=case_id,
            stage="planner",
            event_type="cortex.plan_ready",
            details=plan.to_dict(),
        )

    gate_action = plan.steps[-1]["action"]
    gate_action = {
        **gate_action,
        "proposer": "orchestrator",
        "mission_envelope": MissionEnvelope(
            envelope_id="env-b",
            mission_id="mission-scenario-b",
            approved_by="commander",
        ),
        "approvals": [
            Approval(
                approver=str(item.get("approver", "")),
                proposer=str(item.get("proposer", "orchestrator")),
                channel=str(item.get("channel", "")),
            )
            for item in inputs.approvals
            if not item.get("duress")
        ],
    }

    with tracer.span("gate", stage="gate"):
        verdict = PolicyGate.evaluate(
            gate_action,
            config=PolicyGateConfig(enabled=True),
            evaluator=lambda _action: {"allow": True},
        )
        recorder.record_stage(
            case_id=case_id,
            stage="gate",
            event_type="cortex.gate_verdict",
            details={"allowed": verdict.allowed, "reason": verdict.reason},
        )

    broker_applied = False
    xiid_ref: Optional[XiiDRecordRef] = None
    if verdict.allowed:
        broker = CortexBroker(
            config=PolicyGateConfig(enabled=True),
            evaluator=lambda _action: {"allow": True},
        )
        with tracer.span("broker", stage="broker"):
            change = NetworkChange(
                destination="203.0.113.44",
                operation="block",
                metadata={"case_id": case_id, "plan_id": plan.plan_id},
            )
            broker.execute_network_change(change, gate_action)
            broker_applied = True
            xiid_ref = xiid.record_call(
                case_id=case_id,
                tool_name="xiid.network_block",
                parameters=dict(gate_action.get("parameters") or {}),
                observed_result={"applied": True, "destination": "203.0.113.44"},
            )
            recorder.record_stage(
                case_id=case_id,
                stage="broker",
                event_type="cortex.broker_applied",
                details={"change": asdict(change), "xiid": xiid_ref.to_dict()},
            )

    dropped = ace.dropped_ungrounded if ace is not None else 0
    mrc_after = assess_mrc(
        evidence_count=len(inputs.evidence_ids),
        ace_dropped=dropped,
        gate_allowed=verdict.allowed,
    )

    with tracer.span("verification", stage="verification"):
        verification = verify_and_rollback(audit_log_path=str(audit_path), apply_rollback=False)
        recorder.record_stage(
            case_id=case_id,
            stage="verification",
            event_type="cortex.verification_complete",
            details=verification.to_dict(),
        )

    tracer.force_flush()

    pccp = evaluate_pccp(
        broker_used=broker_applied,
        direct_change_blocked=True,
        gate_fail_closed=True,
        trace_matches_case=verify_trace_matches_case(tracer.local_export()),
        audit_chain_intact=verification.audit_chain_ok,
    )
    recorder.record_stage(
        case_id=case_id,
        stage="verification",
        event_type="cortex.pccp_evaluated",
        details=pccp.to_dict(),
    )

    return ScenarioBResult(
        case_id=case_id,
        inputs=inputs,
        council_output=council_output,
        plan=plan,
        gate_allowed=verdict.allowed,
        gate_reason=verdict.reason,
        broker_applied=broker_applied,
        mrc_before=mrc_before,
        mrc_after=mrc_after,
        verification=verification,
        xiid_ref=xiid_ref,
        audit_log_path=audit_path,
        trace_export_path=tracer.export_path,
        workspace=workspace,
    )


def _default_council_factory(workspace: Path) -> EngineCouncil:
    def proposer(_s: str, _u: str) -> str:
        return "CLAIM|EV-B1,EV-B2|Lateral movement toward 203.0.113.44"

    def challenger(_s: str, _u: str) -> str:
        return ""

    engines = {
        "strategist": RoleEngine(
            role="strategist",
            engine_id="reasoning_engine",
            family="mistral",
            registry=None,  # type: ignore[arg-type]
            runtime_format="gguf",
            model_file="",
            backend_config={},
            generate=proposer,
        ),
        "challenger": RoleEngine(
            role="challenger",
            engine_id="planning_engine",
            family="xai",
            registry=None,  # type: ignore[arg-type]
            runtime_format="gguf",
            model_file="",
            backend_config={},
            generate=challenger,
        ),
    }
    reliability = ReliabilityStore(workspace / "reliability.json")
    return EngineCouncil(
        config_path=Path(__file__).resolve().parents[2] / "configs" / "cortex.yaml",
        reliability=reliability,
        engines=engines,
    )
