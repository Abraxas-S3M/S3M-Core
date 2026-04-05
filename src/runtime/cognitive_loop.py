"""Unified cognitive loop runtime for S3M tactical decision cycles."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

try:
    from src.belief_state import BeliefState, BeliefStore
    from src.belief_state.bayesian_updater import BayesianUpdater, EvidenceBundle

    _BELIEF_AVAILABLE = True
except ImportError:
    _BELIEF_AVAILABLE = False
    BeliefStore = None  # type: ignore[assignment]
    BeliefState = Any  # type: ignore[assignment]
    BayesianUpdater = None  # type: ignore[assignment]
    EvidenceBundle = Any  # type: ignore[assignment]

try:
    from src.decision import ProbabilisticDecisionEngine

    _DECISION_AVAILABLE = True
except ImportError:
    _DECISION_AVAILABLE = False
    ProbabilisticDecisionEngine = None  # type: ignore[assignment]

try:
    from src.cognitive import UnifiedCognitiveEngine

    _COGNITIVE_ENGINE_AVAILABLE = True
except ImportError:
    _COGNITIVE_ENGINE_AVAILABLE = False
    UnifiedCognitiveEngine = None  # type: ignore[assignment]

try:
    from src.replanning import PlanRepairEngine

    _REPLAN_AVAILABLE = True
except ImportError:
    _REPLAN_AVAILABLE = False
    PlanRepairEngine = None  # type: ignore[assignment]

try:
    from src.security.model_trust import ModelTrustRegistry

    _TRUST_AVAILABLE = True
except ImportError:
    _TRUST_AVAILABLE = False
    ModelTrustRegistry = None  # type: ignore[assignment]

try:
    from src.security.inference_monitor import InferenceMonitor

    _INFERENCE_MONITOR_AVAILABLE = True
except ImportError:
    _INFERENCE_MONITOR_AVAILABLE = False
    InferenceMonitor = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """Execution status for one cognitive-loop stage."""

    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class LoopStatus(str, Enum):
    """Overall status for one full cognitive-loop cycle."""

    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    VETOED = "VETOED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAILED = "FAILED"


class LoopConfig(BaseModel):
    """Immutable configuration for S3M runtime behavior under tactical uncertainty."""

    model_config = ConfigDict(frozen=True)

    security_block_on_critical: bool = True
    require_human_review_on_high_anomaly: bool = True
    require_human_review_on_low_confidence: bool = True
    min_decision_confidence: float = Field(default=0.20, ge=0.0, le=1.0)
    replan_on_belief_shift: bool = True
    max_history: int = Field(default=500, ge=1)
    max_audit_entries: int = Field(default=1000, ge=1)
    stage_timeout_ms: float = Field(default=5000.0, gt=0.0)

    @classmethod
    def default(cls) -> "LoopConfig":
        """Return default operating profile for routine mission cycles."""
        return cls()

    @classmethod
    def strict(cls) -> "LoopConfig":
        """Return conservative profile for high-risk mission governance."""
        return cls(
            security_block_on_critical=True,
            min_decision_confidence=0.40,
            require_human_review_on_high_anomaly=True,
        )

    @classmethod
    def permissive(cls) -> "LoopConfig":
        """Return permissive profile for low-threat controlled environments."""
        return cls(
            security_block_on_critical=False,
            min_decision_confidence=0.10,
            require_human_review_on_high_anomaly=False,
        )


class StageResult(BaseModel):
    """Immutable timing and outcome record for one cycle stage."""

    model_config = ConfigDict(frozen=True)

    stage_name: str
    status: StageStatus
    duration_ms: float = Field(ge=0.0)
    detail: str = ""
    error: Optional[str] = None

    def ok(self) -> bool:
        """Return True when a stage completed or was safely skipped."""
        return self.status in {StageStatus.COMPLETED, StageStatus.SKIPPED}


class LoopInput(BaseModel):
    """Immutable operator/runtime payload for one cognitive-loop cycle."""

    model_config = ConfigDict(frozen=True)

    cycle_id: str = Field(default_factory=lambda: str(uuid4()))
    observation_bundle: Optional[Any] = None
    decision_options: List[Any] = Field(default_factory=list)
    current_plan: Optional[Any] = None
    inference_observations: List[Any] = Field(default_factory=list)
    model_ids_to_check: List[str] = Field(default_factory=list)
    author_id: Optional[str] = None
    call_context: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LoopAuditEntry(BaseModel):
    """Immutable audit event for one complete tactical cognitive cycle."""

    model_config = ConfigDict(frozen=True)

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    cycle_id: str
    cycle_number: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    belief_version_before: int
    belief_version_after: int
    belief_updated: bool
    n_decision_options: int = Field(ge=0)
    selected_option_label: Optional[str] = None
    decision_utility: Optional[float] = None
    decision_confidence: Optional[float] = None
    replan_triggered: bool
    replan_trigger_reason: Optional[str] = None
    n_inference_alerts: int = Field(ge=0)
    max_alert_severity: Optional[str] = None
    security_veto_applied: bool
    n_model_ids_checked: int = Field(ge=0)
    all_models_trusted: bool
    requires_human_review: bool
    human_review_reasons: List[str] = Field(default_factory=list)
    stage_timings_ms: Dict[str, float] = Field(default_factory=dict)
    total_ms: float = Field(ge=0.0)
    loop_status: str
    author_id: Optional[str] = None


class LoopOutput(BaseModel):
    """Immutable result artifact for one unified cognitive-loop execution."""

    model_config = ConfigDict(frozen=True)

    cycle_id: str
    cycle_number: int = Field(ge=0)
    loop_status: LoopStatus
    belief_snapshot: Optional[Any] = None
    belief_version: int = 0
    decision_result: Optional[Any] = None
    selected_option_label: Optional[str] = None
    decision_confidence: Optional[float] = None
    repair_result: Optional[Any] = None
    replan_triggered: bool = False
    security_alerts: List[Any] = Field(default_factory=list)
    trust_records: List[Any] = Field(default_factory=list)
    security_veto_applied: bool = False
    veto_reason: Optional[str] = None
    veto_reason_ar: Optional[str] = None
    requires_human_review: bool = False
    human_review_reasons: List[str] = Field(default_factory=list)
    stage_results: List[StageResult]
    audit_entry: LoopAuditEntry
    rationale: str
    rationale_ar: str
    computation_ms: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def all_stages_ok(self) -> bool:
        """Return True when all stages are either completed or safely skipped."""
        return all(stage.ok() for stage in self.stage_results)

    def max_alert_severity(self) -> Optional[str]:
        """Return the highest observed alert severity across security alerts."""
        return _max_severity_from_alerts(self.security_alerts)

    def is_actionable(self) -> bool:
        """Return True when output can be acted on without human intervention."""
        return (
            self.loop_status in {LoopStatus.NOMINAL, LoopStatus.VETOED}
            and not self.requires_human_review
        )


class CognitiveLoop:
    """Single-threaded runtime that chains tactical cognition subsystems per cycle."""

    def __init__(
        self,
        config: Optional[LoopConfig] = None,
        belief_store: Optional[Any] = None,
        bayesian_updater: Optional[Any] = None,
        decision_engine: Optional[Any] = None,
        unified_cognitive_engine: Optional[Any] = None,
        plan_repair_engine: Optional[Any] = None,
        trust_registry: Optional[Any] = None,
        inference_monitor: Optional[Any] = None,
    ) -> None:
        """Initialize loop with optional subsystem instances and immutable config."""
        self.config = config or LoopConfig.default()
        self.belief_store = belief_store
        self.bayesian_updater = bayesian_updater
        self.decision_engine = decision_engine
        self.unified_cognitive_engine = unified_cognitive_engine
        self.plan_repair_engine = plan_repair_engine
        self.trust_registry = trust_registry
        self.inference_monitor = inference_monitor

        if self.unified_cognitive_engine is None and _COGNITIVE_ENGINE_AVAILABLE:
            try:
                self.unified_cognitive_engine = UnifiedCognitiveEngine(
                    decision_engine=self.decision_engine,
                    min_decision_confidence=self.config.min_decision_confidence,
                )
            except Exception:
                self.unified_cognitive_engine = None

        self._belief_store = belief_store
        self._bayesian_updater = bayesian_updater
        self._decision_engine = decision_engine
        self._unified_cognitive_engine = self.unified_cognitive_engine
        self._plan_repair_engine = plan_repair_engine
        self._trust_registry = trust_registry
        self._inference_monitor = inference_monitor

        self._lock = threading.RLock()
        self._cycle_number: int = 0
        self._history: List[LoopOutput] = []
        self._audit_log: List[LoopAuditEntry] = []

    def run(self, input: LoopInput) -> LoopOutput:
        """Execute one full cycle and return an immutable loop output."""
        with self._lock:
            self._cycle_number += 1
            cycle_number = self._cycle_number
            t_start = time.perf_counter()
            stage_results: List[StageResult] = []

            belief_version_before = 0
            belief_version_after = 0
            belief_updated = False
            new_belief_state: Optional[Any] = None

            security_alerts: List[Any] = []
            trust_records: List[Any] = []
            decision_result: Optional[Any] = None
            repair_result: Optional[Any] = None
            replan_triggered = False
            replan_trigger_reason: Optional[str] = None
            security_veto_applied = False
            veto_reason: Optional[str] = None
            veto_reason_ar: Optional[str] = None

            selected_label: Optional[str] = None
            decision_confidence: Optional[float] = None
            decision_utility: Optional[float] = None
            loop_status = LoopStatus.DEGRADED
            requires_human_review = False
            human_review_reasons: List[str] = []
            max_severity: Optional[str] = None
            all_models_trusted = True

            t_stage = time.perf_counter()
            ingest_status = StageStatus.COMPLETED
            ingest_detail = "Input validated"
            ingest_error: Optional[str] = None
            try:
                if (
                    _BELIEF_AVAILABLE
                    and input.observation_bundle is not None
                    and not hasattr(input.observation_bundle, "bundle_id")
                ):
                    raise ValueError("observation_bundle must expose bundle_id")
            except Exception as exc:
                ingest_status = StageStatus.FAILED
                ingest_detail = "Input validation failed"
                ingest_error = str(exc)
            ingest_sr = StageResult(
                stage_name="INGEST",
                status=ingest_status,
                duration_ms=self._elapsed_ms(t_stage),
                detail=ingest_detail,
                error=ingest_error,
            )
            stage_results.append(ingest_sr)
            self._check_stage_overrun(ingest_sr.stage_name, ingest_sr.duration_ms)

            t_stage = time.perf_counter()
            belief_status = StageStatus.SKIPPED
            belief_detail = "No observation_bundle or subsystem unavailable"
            belief_error: Optional[str] = None
            try:
                if _BELIEF_AVAILABLE and self.belief_store is not None:
                    current_state = self.belief_store.current()
                    belief_version_before = int(getattr(current_state, "version", 0))
                    belief_version_after = belief_version_before
                    new_belief_state = current_state

                if (
                    _BELIEF_AVAILABLE
                    and self.belief_store is not None
                    and self.bayesian_updater is not None
                    and input.observation_bundle is not None
                ):
                    prior_state = self.belief_store.current()
                    belief_version_before = int(getattr(prior_state, "version", 0))
                    bayesian_result = self.bayesian_updater.compute(
                        prior_state, input.observation_bundle
                    )
                    new_belief_state = self.belief_store.apply(
                        bayesian_result.update,
                        author=input.author_id or "cognitive_loop",
                    )
                    belief_version_after = int(
                        getattr(new_belief_state, "version", belief_version_before)
                    )
                    belief_updated = True
                    belief_status = StageStatus.COMPLETED
                    belief_detail = (
                        f"Belief updated v{belief_version_before}->v{belief_version_after}"
                    )
            except Exception as exc:
                belief_status = StageStatus.FAILED
                belief_error = str(exc)
                belief_detail = "Belief update failed"
                belief_updated = False
                if _BELIEF_AVAILABLE and self.belief_store is not None:
                    try:
                        new_belief_state = self.belief_store.current()
                        belief_version_after = int(
                            getattr(new_belief_state, "version", belief_version_before)
                        )
                    except Exception:
                        new_belief_state = None
            belief_sr = StageResult(
                stage_name="BELIEF",
                status=belief_status,
                duration_ms=self._elapsed_ms(t_stage),
                detail=belief_detail,
                error=belief_error,
            )
            stage_results.append(belief_sr)
            self._check_stage_overrun(belief_sr.stage_name, belief_sr.duration_ms)

            t_stage = time.perf_counter()
            security_status = StageStatus.SKIPPED
            security_detail_parts: List[str] = []
            security_errors: List[str] = []
            monitor_ran = False
            trust_ran = False
            try:
                if (
                    _INFERENCE_MONITOR_AVAILABLE
                    and self.inference_monitor is not None
                    and input.inference_observations
                ):
                    try:
                        security_alerts = self.inference_monitor.observe_batch(
                            input.inference_observations
                        )
                        monitor_ran = True
                        security_detail_parts.append(
                            f"{len(security_alerts)} alerts from "
                            f"{len(input.inference_observations)} observations"
                        )
                    except Exception as exc:
                        security_errors.append(f"monitor: {exc}")
                else:
                    security_detail_parts.append("monitor skipped")

                if (
                    _TRUST_AVAILABLE
                    and self.trust_registry is not None
                    and input.model_ids_to_check
                ):
                    for model_id in input.model_ids_to_check:
                        try:
                            trust_record = self.trust_registry.attest(
                                model_id,
                                call_context={
                                    "cycle_id": input.cycle_id,
                                    "author": input.author_id,
                                    **input.call_context,
                                },
                            )
                            trust_records.append(trust_record)
                            trust_ran = True
                        except Exception as exc:
                            security_errors.append(f"trust[{model_id}]: {exc}")
                    if trust_ran:
                        security_detail_parts.append(
                            f"{len(trust_records)} models attested"
                        )
                else:
                    security_detail_parts.append("trust skipped")

                if security_errors:
                    security_status = StageStatus.FAILED
                elif monitor_ran or trust_ran:
                    security_status = StageStatus.COMPLETED
                else:
                    security_status = StageStatus.SKIPPED
            except Exception as exc:
                security_status = StageStatus.FAILED
                security_errors.append(str(exc))
            security_sr = StageResult(
                stage_name="SECURITY_MONITOR",
                status=security_status,
                duration_ms=self._elapsed_ms(t_stage),
                detail="; ".join(security_detail_parts),
                error=" | ".join(security_errors) if security_errors else None,
            )
            stage_results.append(security_sr)
            self._check_stage_overrun(security_sr.stage_name, security_sr.duration_ms)

            t_stage = time.perf_counter()
            decision_status = StageStatus.SKIPPED
            decision_detail = "No decision_options or subsystem unavailable"
            decision_error: Optional[str] = None
            try:
                if input.decision_options:
                    belief_for_decision = new_belief_state
                    if new_belief_state is not None:
                        # DecisionResult expects a string snapshot ID; BeliefState exposes UUID.
                        belief_for_decision = SimpleNamespace(
                            state_id=str(getattr(new_belief_state, "state_id", "")),
                            confidence_distribution=getattr(
                                new_belief_state, "confidence_distribution", {}
                            ),
                            doctrine_context=getattr(new_belief_state, "doctrine_context", None),
                            entropy=getattr(new_belief_state, "entropy", lambda: 0.0),
                        )
                    if self.unified_cognitive_engine is not None:
                        decision_result = self.unified_cognitive_engine.evaluate(
                            options=input.decision_options,
                            belief_state=belief_for_decision,
                            author_id=input.author_id,
                            decision_engine=self.decision_engine,
                        )
                    elif _DECISION_AVAILABLE and self.decision_engine is not None:
                        decision_result = self.decision_engine.evaluate(
                            options=input.decision_options,
                            belief_state=belief_for_decision,
                            author_id=input.author_id,
                        )

                    if decision_result is not None:
                        selected = decision_result.result.selected
                        decision_status = StageStatus.COMPLETED
                        decision_detail = (
                            f"Selected: {selected.option.label} "
                            f"utility={selected.utility_score:.4f}"
                        )
            except Exception as exc:
                decision_status = StageStatus.FAILED
                decision_detail = "Decision evaluation failed"
                decision_error = str(exc)
                decision_result = None
            decision_sr = StageResult(
                stage_name="DECISION",
                status=decision_status,
                duration_ms=self._elapsed_ms(t_stage),
                detail=decision_detail,
                error=decision_error,
            )
            stage_results.append(decision_sr)
            self._check_stage_overrun(decision_sr.stage_name, decision_sr.duration_ms)

            t_stage = time.perf_counter()
            replan_status = StageStatus.SKIPPED
            replan_detail = ""
            replan_error: Optional[str] = None
            try:
                if (
                    _REPLAN_AVAILABLE
                    and self.plan_repair_engine is not None
                    and input.current_plan is not None
                    and self.config.replan_on_belief_shift
                ):
                    repair_result = self.plan_repair_engine.evaluate(
                        plan=input.current_plan,
                        belief_state=new_belief_state,
                        author_id=input.author_id,
                    )
                    shift_report = getattr(repair_result, "shift_report", None)
                    repair_required = getattr(shift_report, "repair_required", None)
                    if callable(repair_required):
                        replan_triggered = bool(repair_required())
                    else:
                        replan_triggered = bool(
                            getattr(repair_result, "replan_triggered", False)
                        )

                    if replan_triggered:
                        triggers = getattr(shift_report, "triggers", [])
                        trigger_names = [
                            str(getattr(trigger, "value", trigger))
                            for trigger in triggers
                        ]
                        replan_trigger_reason = ", ".join(trigger_names) or "belief shift"
                    replan_status = (
                        StageStatus.COMPLETED
                        if replan_triggered
                        else StageStatus.SKIPPED
                    )
                    replan_detail = (
                        f"Repair required={replan_triggered} "
                        f"triggers={replan_trigger_reason}"
                    )
            except Exception as exc:
                replan_status = StageStatus.FAILED
                replan_detail = "Plan repair evaluation failed"
                replan_error = str(exc)
                repair_result = None
                replan_triggered = False
                replan_trigger_reason = None
            replan_sr = StageResult(
                stage_name="REPLAN",
                status=replan_status,
                duration_ms=self._elapsed_ms(t_stage),
                detail=replan_detail,
                error=replan_error,
            )
            stage_results.append(replan_sr)
            self._check_stage_overrun(replan_sr.stage_name, replan_sr.duration_ms)

            t_stage = time.perf_counter()
            veto_status = StageStatus.SKIPPED
            veto_detail = "Veto applied=False"
            veto_error: Optional[str] = None
            try:
                max_severity = self._max_severity(security_alerts)
                if (
                    self.config.security_block_on_critical
                    and max_severity == "CRITICAL"
                    and decision_result is not None
                ):
                    security_veto_applied = True
                    recommended_action = None
                    if security_alerts:
                        recommended_action = getattr(
                            security_alerts[-1], "recommended_action", None
                        )
                    veto_reason = (
                        "Security veto: CRITICAL inference anomaly detected on "
                        f"{len(security_alerts)} model(s). Primary decision overridden."
                    )
                    if recommended_action:
                        veto_reason += f" Recommended action: {recommended_action}"
                    veto_reason_ar = (
                        "حظر أمني: تم رصد شذوذ استدلال حرج في "
                        f"{len(security_alerts)} نموذج. تم تجاوز القرار الأساسي."
                    )
                    veto_status = StageStatus.COMPLETED
                    veto_detail = "Veto applied=True"
            except Exception as exc:
                veto_status = StageStatus.FAILED
                veto_detail = "Veto evaluation failed"
                veto_error = str(exc)
                security_veto_applied = False
                veto_reason = None
                veto_reason_ar = None
            veto_sr = StageResult(
                stage_name="VETO",
                status=veto_status,
                duration_ms=self._elapsed_ms(t_stage),
                detail=veto_detail,
                error=veto_error,
            )
            stage_results.append(veto_sr)
            self._check_stage_overrun(veto_sr.stage_name, veto_sr.duration_ms)

            t_stage = time.perf_counter()
            audit_status = StageStatus.COMPLETED
            audit_detail = "Audit context prepared"
            audit_error: Optional[str] = None
            try:
                failed_stages = {
                    stage.stage_name
                    for stage in stage_results
                    if stage.status == StageStatus.FAILED
                }
                if failed_stages:
                    if "BELIEF" in failed_stages or "DECISION" in failed_stages:
                        loop_status = LoopStatus.FAILED
                    else:
                        loop_status = LoopStatus.DEGRADED
                elif security_veto_applied:
                    loop_status = LoopStatus.VETOED
                elif any(
                    stage.status in {StageStatus.SKIPPED, StageStatus.DEGRADED}
                    for stage in stage_results
                ):
                    loop_status = LoopStatus.DEGRADED
                else:
                    loop_status = LoopStatus.NOMINAL

                if decision_result is not None:
                    selected = decision_result.result.selected
                    selected_label = getattr(selected.option, "label", None)
                    decision_confidence = float(
                        getattr(decision_result.result, "confidence", 0.0)
                    )
                    decision_utility = float(getattr(selected, "utility_score", 0.0))

                human_review_reasons = []
                if (
                    self.config.require_human_review_on_high_anomaly
                    and max_severity in {"HIGH", "CRITICAL"}
                ):
                    human_review_reasons.append(
                        f"Inference anomaly severity={max_severity}"
                    )

                if (
                    self.config.require_human_review_on_low_confidence
                    and decision_result is not None
                ):
                    confidence_metric = self._decision_confidence_metric(decision_result)
                    if (
                        confidence_metric is not None
                        and confidence_metric < self.config.min_decision_confidence
                    ):
                        human_review_reasons.append(
                            f"Low decision confidence={confidence_metric:.4f}"
                        )

                if (
                    decision_result is not None
                    and bool(
                        getattr(decision_result.result, "requires_human_review", False)
                    )
                ):
                    human_review_reasons.append(
                        "DecisionEngine flagged human review required"
                    )

                for trust_record in trust_records:
                    if (
                        bool(getattr(trust_record, "requires_human_review", False))
                        and not bool(getattr(trust_record, "blocked", False))
                    ):
                        human_review_reasons.append(
                            "Model trust attestation requires review"
                        )
                        break

                requires_human_review = len(human_review_reasons) > 0
                if requires_human_review and loop_status == LoopStatus.NOMINAL:
                    loop_status = LoopStatus.HUMAN_REVIEW

                all_models_trusted = (
                    all(not bool(getattr(record, "blocked", False)) for record in trust_records)
                    if trust_records
                    else True
                )
            except Exception as exc:
                loop_status = LoopStatus.FAILED
                requires_human_review = True
                human_review_reasons = ["Audit preparation failure"]
                audit_status = StageStatus.FAILED
                audit_detail = "Audit context failed"
                audit_error = str(exc)
            audit_sr = StageResult(
                stage_name="AUDIT",
                status=audit_status,
                duration_ms=self._elapsed_ms(t_stage),
                detail=audit_detail,
                error=audit_error,
            )
            stage_results.append(audit_sr)
            self._check_stage_overrun(audit_sr.stage_name, audit_sr.duration_ms)

            t_stage = time.perf_counter()
            output_error: Optional[str] = None
            output_status = StageStatus.COMPLETED
            output_detail = "Loop output assembled"
            output: Optional[LoopOutput] = None

            try:
                stage_timings = {stage.stage_name: stage.duration_ms for stage in stage_results}
                total_ms = (time.perf_counter() - t_start) * 1000.0
                output_sr = StageResult(
                    stage_name="OUTPUT",
                    status=StageStatus.COMPLETED,
                    duration_ms=0.0,
                    detail="Loop output assembled",
                )
                full_stage_results = [*stage_results, output_sr]
                stage_timings["OUTPUT"] = 0.0

                audit_entry = LoopAuditEntry(
                    cycle_id=input.cycle_id,
                    cycle_number=cycle_number,
                    belief_version_before=belief_version_before,
                    belief_version_after=belief_version_after,
                    belief_updated=belief_updated,
                    n_decision_options=len(input.decision_options),
                    selected_option_label=selected_label,
                    decision_utility=decision_utility,
                    decision_confidence=decision_confidence,
                    replan_triggered=replan_triggered,
                    replan_trigger_reason=replan_trigger_reason,
                    n_inference_alerts=len(security_alerts),
                    max_alert_severity=max_severity,
                    security_veto_applied=security_veto_applied,
                    n_model_ids_checked=len(input.model_ids_to_check),
                    all_models_trusted=all_models_trusted,
                    requires_human_review=requires_human_review,
                    human_review_reasons=human_review_reasons,
                    stage_timings_ms=stage_timings,
                    total_ms=total_ms,
                    loop_status=loop_status.value,
                    author_id=input.author_id,
                )

                output = LoopOutput(
                    cycle_id=input.cycle_id,
                    cycle_number=cycle_number,
                    loop_status=loop_status,
                    belief_snapshot=new_belief_state,
                    belief_version=belief_version_after,
                    decision_result=decision_result,
                    selected_option_label=selected_label,
                    decision_confidence=decision_confidence,
                    repair_result=repair_result,
                    replan_triggered=replan_triggered,
                    security_alerts=security_alerts,
                    trust_records=trust_records,
                    security_veto_applied=security_veto_applied,
                    veto_reason=veto_reason,
                    veto_reason_ar=veto_reason_ar,
                    requires_human_review=requires_human_review,
                    human_review_reasons=human_review_reasons,
                    stage_results=full_stage_results,
                    audit_entry=audit_entry,
                    rationale="",
                    rationale_ar="",
                    computation_ms=total_ms,
                )
                output = output.model_copy(
                    update={
                        "rationale": self._build_rationale_en(output, input),
                        "rationale_ar": self._build_rationale_ar(output, input),
                    }
                )
            except Exception as exc:
                output_status = StageStatus.FAILED
                output_detail = "Fallback output assembled after output failure"
                output_error = str(exc)

            output_duration = self._elapsed_ms(t_stage)
            output_sr_final = StageResult(
                stage_name="OUTPUT",
                status=output_status,
                duration_ms=output_duration,
                detail=output_detail,
                error=output_error,
            )
            self._check_stage_overrun(output_sr_final.stage_name, output_sr_final.duration_ms)

            if output is None:
                safe_stage_results = [*stage_results, output_sr_final]
                total_ms = (time.perf_counter() - t_start) * 1000.0
                if output_status == StageStatus.FAILED:
                    loop_status = LoopStatus.FAILED
                safe_audit = LoopAuditEntry(
                    cycle_id=input.cycle_id,
                    cycle_number=cycle_number,
                    belief_version_before=belief_version_before,
                    belief_version_after=belief_version_after,
                    belief_updated=belief_updated,
                    n_decision_options=len(input.decision_options),
                    selected_option_label=selected_label,
                    decision_utility=decision_utility,
                    decision_confidence=decision_confidence,
                    replan_triggered=replan_triggered,
                    replan_trigger_reason=replan_trigger_reason,
                    n_inference_alerts=len(security_alerts),
                    max_alert_severity=max_severity,
                    security_veto_applied=security_veto_applied,
                    n_model_ids_checked=len(input.model_ids_to_check),
                    all_models_trusted=all_models_trusted,
                    requires_human_review=requires_human_review,
                    human_review_reasons=human_review_reasons,
                    stage_timings_ms={
                        stage.stage_name: stage.duration_ms for stage in safe_stage_results
                    },
                    total_ms=total_ms,
                    loop_status=loop_status.value,
                    author_id=input.author_id,
                )
                output = LoopOutput(
                    cycle_id=input.cycle_id,
                    cycle_number=cycle_number,
                    loop_status=loop_status,
                    belief_snapshot=new_belief_state,
                    belief_version=belief_version_after,
                    decision_result=decision_result,
                    selected_option_label=selected_label,
                    decision_confidence=decision_confidence,
                    repair_result=repair_result,
                    replan_triggered=replan_triggered,
                    security_alerts=security_alerts,
                    trust_records=trust_records,
                    security_veto_applied=security_veto_applied,
                    veto_reason=veto_reason,
                    veto_reason_ar=veto_reason_ar,
                    requires_human_review=requires_human_review,
                    human_review_reasons=human_review_reasons,
                    stage_results=safe_stage_results,
                    audit_entry=safe_audit,
                    rationale="",
                    rationale_ar="",
                    computation_ms=total_ms,
                )
                output = output.model_copy(
                    update={
                        "rationale": self._build_rationale_en(output, input),
                        "rationale_ar": self._build_rationale_ar(output, input),
                    }
                )
            else:
                updated_stage_results = list(output.stage_results)
                updated_stage_results[-1] = output_sr_final
                stage_timings = {stage.stage_name: stage.duration_ms for stage in updated_stage_results}
                updated_audit = output.audit_entry.model_copy(
                    update={
                        "stage_timings_ms": stage_timings,
                        "total_ms": output.computation_ms,
                    }
                )
                output = output.model_copy(
                    update={
                        "stage_results": updated_stage_results,
                        "audit_entry": updated_audit,
                    }
                )

            self._history.append(output)
            while len(self._history) > self.config.max_history:
                self._history.pop(0)

            self._audit_log.append(output.audit_entry)
            while len(self._audit_log) > self.config.max_audit_entries:
                self._audit_log.pop(0)

            return output

    def run_batch(self, inputs: List[LoopInput]) -> List[LoopOutput]:
        """Run multiple cycle inputs sequentially and return all outputs."""
        return [self.run(item) for item in inputs]

    def history(self, n: int = 10) -> List[LoopOutput]:
        """Return the last n loop outputs ordered from oldest to newest."""
        if n <= 0:
            return []
        return list(self._history[-n:])

    def audit_log(self, n: int = 50) -> List[LoopAuditEntry]:
        """Return the last n audit entries ordered from oldest to newest."""
        if n <= 0:
            return []
        return list(self._audit_log[-n:])

    def current_belief(self) -> Optional[Any]:
        """Return the current belief snapshot when belief subsystem is available."""
        if _BELIEF_AVAILABLE and self.belief_store is not None:
            try:
                return self.belief_store.current()
            except Exception:
                return None
        return None

    def summary(self) -> Dict[str, Any]:
        """Return aggregate operational counters for executed loop history."""
        last_output = self._history[-1] if self._history else None
        return {
            "cycle_number": self._cycle_number,
            "total_cycles_run": len(self._history),
            "n_alerts_total": sum(len(item.security_alerts) for item in self._history),
            "n_replans_total": sum(1 for item in self._history if item.replan_triggered),
            "n_vetoes_total": sum(
                1 for item in self._history if item.security_veto_applied
            ),
            "n_human_reviews_total": sum(
                1 for item in self._history if item.requires_human_review
            ),
            "last_loop_status": last_output.loop_status.value if last_output else None,
            "last_belief_version": last_output.belief_version if last_output else None,
            "subsystems_available": {
                "belief": _BELIEF_AVAILABLE,
                "decision": _DECISION_AVAILABLE,
                "unified_cognitive_engine": self.unified_cognitive_engine is not None,
                "replanning": _REPLAN_AVAILABLE,
                "trust_registry": _TRUST_AVAILABLE,
                "inference_monitor": _INFERENCE_MONITOR_AVAILABLE,
            },
        }

    def _elapsed_ms(self, t_start: float) -> float:
        """Return elapsed milliseconds using perf_counter for timing integrity."""
        return max(0.0, (time.perf_counter() - t_start) * 1000.0)

    def _max_severity(self, alerts: List[Any]) -> Optional[str]:
        """Return highest severity class found in security alerts."""
        return _max_severity_from_alerts(alerts)

    def _build_rationale_en(self, output: LoopOutput, input: LoopInput) -> str:
        """Build deterministic English rationale for mission audit and operator review."""
        before = output.audit_entry.belief_version_before
        after = output.audit_entry.belief_version_after
        selected = output.selected_option_label or "None"
        utility_text = (
            f"{output.audit_entry.decision_utility:.4f}"
            if output.audit_entry.decision_utility is not None
            else "n/a"
        )
        replan_text = (
            f"triggered ({output.audit_entry.replan_trigger_reason})"
            if output.replan_triggered
            else "not triggered"
        )
        max_sev = output.max_alert_severity() or "NONE"
        review_text = (
            "; ".join(output.human_review_reasons)
            if output.requires_human_review
            else "None"
        )
        return (
            f"Cycle {output.cycle_number} ({input.cycle_id}) completed with status "
            f"{output.loop_status.value}. Belief version {before}->{after}. "
            f"Selected option: {selected} (utility={utility_text}). "
            f"Replan was {replan_text}. Security alerts={len(output.security_alerts)} "
            f"(max severity={max_sev}). Veto applied={output.security_veto_applied}. "
            f"Human review required={output.requires_human_review} "
            f"(reasons={review_text}). Total computation={output.computation_ms:.3f} ms."
        )

    def _build_rationale_ar(self, output: LoopOutput, input: LoopInput) -> str:
        """Build deterministic Arabic rationale for bilingual tactical governance."""
        before = output.audit_entry.belief_version_before
        after = output.audit_entry.belief_version_after
        selected = output.selected_option_label or "لا يوجد"
        utility_text = (
            f"{output.audit_entry.decision_utility:.4f}"
            if output.audit_entry.decision_utility is not None
            else "غير متاح"
        )
        replan_text = (
            f"تم التفعيل ({output.audit_entry.replan_trigger_reason})"
            if output.replan_triggered
            else "لم يتم التفعيل"
        )
        max_sev = output.max_alert_severity() or "NONE"
        review_text = (
            "؛ ".join(output.human_review_reasons)
            if output.requires_human_review
            else "لا يوجد"
        )
        return (
            f"الدورة {output.cycle_number} ({input.cycle_id}) انتهت بحالة "
            f"{output.loop_status.value}. إصدار حالة الاعتقاد {before}->{after}. "
            f"الخيار المختار: {selected} (المنفعة={utility_text}). "
            f"إعادة التخطيط: {replan_text}. عدد تنبيهات الأمن={len(output.security_alerts)} "
            f"(أعلى شدة={max_sev}). تطبيق الحظر الأمني={output.security_veto_applied}. "
            f"يتطلب مراجعة بشرية={output.requires_human_review} "
            f"(الأسباب={review_text}). زمن الحساب الكلي={output.computation_ms:.3f} مللي ثانية."
        )

    def _check_stage_overrun(self, stage_name: str, duration_ms: float) -> None:
        """Log timing warning when a stage exceeds configured budget."""
        if duration_ms > self.config.stage_timeout_ms:
            logger.warning(
                "CognitiveLoop stage %s exceeded budget %.2f ms > %.2f ms",
                stage_name,
                duration_ms,
                self.config.stage_timeout_ms,
            )

    def _decision_confidence_metric(self, decision_result: Any) -> Optional[float]:
        """Compute confidence metric from decision record using tactical success terms."""
        try:
            confidence = float(getattr(decision_result.result, "confidence", 0.0))
            selected = getattr(decision_result.result, "selected", None)
            option = getattr(selected, "option", None)
            probability = getattr(option, "probability_of_success", None)
            if probability is None:
                return confidence
            return float(probability) * confidence
        except Exception:
            return None


def _max_severity_from_alerts(alerts: List[Any]) -> Optional[str]:
    """Resolve highest alert severity string from arbitrary alert objects."""
    if not alerts:
        return None
    severity_order = ["NEGLIGIBLE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    best = -1
    best_label: Optional[str] = None
    for alert in alerts:
        severity_value: Optional[str] = None
        anomaly_score = getattr(alert, "anomaly_score", None)
        if anomaly_score is not None:
            severity = getattr(anomaly_score, "severity", None)
            if severity is not None:
                severity_value = str(getattr(severity, "value", severity))
        if severity_value is None:
            severity_value = str(getattr(alert, "severity", ""))
        if severity_value in severity_order:
            rank = severity_order.index(severity_value)
            if rank > best:
                best = rank
                best_label = severity_value
    return best_label


def create_cognitive_loop(
    config: Optional[LoopConfig] = None,
    ewma_alpha: float = 0.1,
    monitor_min_baseline: int = 10,
    decision_weights: Optional[Any] = None,
    roe: Optional[Any] = None,
) -> CognitiveLoop:
    """
    Create a cognitive loop with best-effort subsystem wiring and graceful degradation.
    """
    belief_store = None
    bayesian_updater = None
    decision_engine = None
    unified_cognitive_engine = None
    plan_repair_engine = None
    trust_registry = None
    inference_monitor = None

    try:
        from src.belief_state import BeliefStore as _BeliefStore
        from src.belief_state.bayesian_updater import BayesianUpdater as _BayesianUpdater

        belief_store = _BeliefStore()
        bayesian_updater = _BayesianUpdater()
    except ImportError:
        pass

    try:
        from src.decision import ProbabilisticDecisionEngine as _ProbabilisticDecisionEngine

        decision_engine = _ProbabilisticDecisionEngine(weights=decision_weights, roe=roe)
    except ImportError:
        pass

    if _COGNITIVE_ENGINE_AVAILABLE:
        try:
            unified_cognitive_engine = UnifiedCognitiveEngine(
                decision_engine=decision_engine,
                min_decision_confidence=(config or LoopConfig.default()).min_decision_confidence,
            )
        except Exception:
            unified_cognitive_engine = None

    try:
        from src.replanning import PlanRepairEngine as _PlanRepairEngine

        plan_repair_engine = _PlanRepairEngine()
    except ImportError:
        pass

    try:
        from src.security.inference_monitor import (
            InferenceMonitor as _InferenceMonitor,
            MonitorConfig as _MonitorConfig,
        )

        inference_monitor = _InferenceMonitor(
            _MonitorConfig(
                ewma_alpha=ewma_alpha,
                min_baseline_observations=monitor_min_baseline,
            )
        )
    except ImportError:
        pass

    return CognitiveLoop(
        config=config or LoopConfig.default(),
        belief_store=belief_store,
        bayesian_updater=bayesian_updater,
        decision_engine=decision_engine,
        unified_cognitive_engine=unified_cognitive_engine,
        plan_repair_engine=plan_repair_engine,
        trust_registry=trust_registry,
        inference_monitor=inference_monitor,
    )
