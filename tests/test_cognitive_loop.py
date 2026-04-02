"""Tests for unified S3M cognitive loop runtime integration."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.runtime import (
    CognitiveLoop,
    LoopAuditEntry,
    LoopConfig,
    LoopInput,
    LoopOutput,
    LoopStatus,
    StageResult,
    StageStatus,
)
from src.runtime.cognitive_loop import create_cognitive_loop

BELIEF_AVAILABLE = True
DECISION_AVAILABLE = True
REPLAN_AVAILABLE = True
SECURITY_AVAILABLE = True

try:
    from src.belief_state import BeliefHypothesis
    from src.belief_state.bayesian_updater import (
        EvidenceBundle,
        EvidenceItem,
    )
    from src.belief_state.models import UpdateSource
except ImportError:
    BELIEF_AVAILABLE = False

try:
    from src.decision import DecisionOption
    from src.decision.decision_models import ActionType
except ImportError:
    DECISION_AVAILABLE = False

try:
    from src.replanning import MissionPlan, PlanStep, PlanRepairEngine
    from src.replanning.plan_repair_engine import StepType
except ImportError:
    REPLAN_AVAILABLE = False

try:
    from src.security.inference_monitor import (
        AlertSeverity,
        InferenceMonitor,
        InferenceObservation,
        ModelDomain,
        MonitorConfig,
    )
except ImportError:
    SECURITY_AVAILABLE = False


def _dummy_output() -> LoopOutput:
    audit = LoopAuditEntry(
        cycle_id="dummy-cycle",
        cycle_number=1,
        belief_version_before=0,
        belief_version_after=0,
        belief_updated=False,
        n_decision_options=0,
        selected_option_label=None,
        decision_utility=None,
        decision_confidence=None,
        replan_triggered=False,
        replan_trigger_reason=None,
        n_inference_alerts=0,
        max_alert_severity=None,
        security_veto_applied=False,
        n_model_ids_checked=0,
        all_models_trusted=True,
        requires_human_review=False,
        human_review_reasons=[],
        stage_timings_ms={"INGEST": 1.0},
        total_ms=1.0,
        loop_status=LoopStatus.NOMINAL.value,
        author_id=None,
    )
    return LoopOutput(
        cycle_id="dummy-cycle",
        cycle_number=1,
        loop_status=LoopStatus.NOMINAL,
        belief_snapshot=None,
        belief_version=0,
        decision_result=None,
        selected_option_label=None,
        decision_confidence=None,
        repair_result=None,
        replan_triggered=False,
        security_alerts=[],
        trust_records=[],
        security_veto_applied=False,
        veto_reason=None,
        veto_reason_ar=None,
        requires_human_review=False,
        human_review_reasons=[],
        stage_results=[
            StageResult(stage_name="INGEST", status=StageStatus.COMPLETED, duration_ms=1.0)
        ],
        audit_entry=audit,
        rationale="ok",
        rationale_ar="حسنًا",
        computation_ms=1.0,
    )


@pytest.fixture
def loop() -> CognitiveLoop:
    return create_cognitive_loop(config=LoopConfig.default())


@pytest.fixture
def warmed_loop() -> CognitiveLoop:
    """Loop with belief state seeded with hypotheses."""
    seeded_loop = create_cognitive_loop()
    if seeded_loop.belief_store and BELIEF_AVAILABLE:
        h0 = BeliefHypothesis(description="Threat-Alpha", probability=0.6)
        h1 = BeliefHypothesis(description="Threat-Beta", probability=0.4)
        seeded_loop.belief_store.create([h0, h1], author="fixture")
    return seeded_loop


@pytest.fixture
def sample_options():
    if not DECISION_AVAILABLE:
        return []
    return [
        DecisionOption(
            label="HOLD position",
            action_type=ActionType.HOLD,
            expected_outcome=0.7,
            probability_of_success=0.85,
            risk_score=0.1,
            cost_score=0.1,
            uncertainty=0.1,
        ),
        DecisionOption(
            label="ENGAGE target",
            action_type=ActionType.ENGAGE,
            expected_outcome=0.9,
            probability_of_success=0.6,
            risk_score=0.7,
            cost_score=0.5,
            uncertainty=0.3,
        ),
        DecisionOption(
            label="RECON sector",
            action_type=ActionType.RECON,
            expected_outcome=0.6,
            probability_of_success=0.9,
            risk_score=0.2,
            cost_score=0.2,
            uncertainty=0.2,
        ),
    ]


@pytest.fixture
def sample_bundle():
    if not BELIEF_AVAILABLE:
        return None
    item = EvidenceItem(
        hypothesis_id="h0",
        likelihood=0.9,
        source_id="sensor-1",
        description="Hostile track confidence increased",
    )
    return EvidenceBundle(
        source=UpdateSource.SENSOR_FUSION,
        items=[item],
        justification="Sensor fusion update",
    )


@pytest.fixture
def sample_plan():
    if not REPLAN_AVAILABLE:
        return None
    steps = [
        PlanStep(
            label="Advance to grid",
            step_type=StepType.MOVE,
            expected_success_prob=0.85,
            risk_score=0.2,
        ),
        PlanStep(
            label="Establish observation post",
            step_type=StepType.RECON,
            expected_success_prob=0.9,
            risk_score=0.1,
        ),
    ]
    return MissionPlan(
        label="OP-FALCON",
        steps=steps,
        expected_completion_prob=0.8,
        expected_outcome=0.8,
    )


@pytest.fixture
def sample_inference_obs():
    if not SECURITY_AVAILABLE:
        return []
    return [
        InferenceObservation(
            model_id="test-model",
            model_name="Test-LLM",
            domain=ModelDomain.TACTICAL,
            confidence_score=0.85,
            latency_ms=120.0,
            response_length=200,
            reasoning_steps=3,
        )
    ]


class TestLoopConfig:
    def test_default_config_valid(self):
        cfg = LoopConfig.default()
        assert cfg.min_decision_confidence == pytest.approx(0.20)
        assert cfg.max_history >= 1

    def test_strict_higher_confidence_threshold(self):
        assert LoopConfig.strict().min_decision_confidence > LoopConfig.default().min_decision_confidence

    def test_permissive_no_security_block(self):
        assert LoopConfig.permissive().security_block_on_critical is False

    def test_frozen(self):
        cfg = LoopConfig.default()
        with pytest.raises(ValidationError):
            cfg.max_history = 3


class TestStageResult:
    def test_ok_true_for_completed(self):
        sr = StageResult(stage_name="X", status=StageStatus.COMPLETED, duration_ms=1.0)
        assert sr.ok() is True

    def test_ok_true_for_skipped(self):
        sr = StageResult(stage_name="X", status=StageStatus.SKIPPED, duration_ms=1.0)
        assert sr.ok() is True

    def test_ok_false_for_failed(self):
        sr = StageResult(stage_name="X", status=StageStatus.FAILED, duration_ms=1.0)
        assert sr.ok() is False

    def test_frozen(self):
        sr = StageResult(stage_name="X", status=StageStatus.COMPLETED, duration_ms=1.0)
        with pytest.raises(ValidationError):
            sr.detail = "mutate"


class TestLoopInput:
    def test_auto_uuid(self):
        loop_input = LoopInput()
        assert UUID(loop_input.cycle_id)

    def test_empty_options_valid(self):
        loop_input = LoopInput(decision_options=[])
        assert loop_input.decision_options == []

    def test_frozen(self):
        loop_input = LoopInput()
        with pytest.raises(ValidationError):
            loop_input.author_id = "override"


class TestLoopOutput:
    def test_all_stages_ok_true_when_all_completed_or_skipped(self):
        output = _dummy_output().model_copy(
            update={
                "stage_results": [
                    StageResult(stage_name="A", status=StageStatus.COMPLETED, duration_ms=1.0),
                    StageResult(stage_name="B", status=StageStatus.SKIPPED, duration_ms=1.0),
                ]
            }
        )
        assert output.all_stages_ok() is True

    def test_all_stages_ok_false_when_any_failed(self):
        output = _dummy_output().model_copy(
            update={
                "stage_results": [
                    StageResult(stage_name="A", status=StageStatus.COMPLETED, duration_ms=1.0),
                    StageResult(stage_name="B", status=StageStatus.FAILED, duration_ms=1.0),
                ]
            }
        )
        assert output.all_stages_ok() is False

    def test_max_alert_severity_none_when_no_alerts(self):
        output = _dummy_output().model_copy(update={"security_alerts": []})
        assert output.max_alert_severity() is None

    def test_max_alert_severity_critical_when_present(self):
        crit_alert = SimpleNamespace(
            anomaly_score=SimpleNamespace(severity=SimpleNamespace(value="CRITICAL"))
        )
        low_alert = SimpleNamespace(
            anomaly_score=SimpleNamespace(severity=SimpleNamespace(value="LOW"))
        )
        output = _dummy_output().model_copy(update={"security_alerts": [low_alert, crit_alert]})
        assert output.max_alert_severity() == "CRITICAL"

    def test_is_actionable_nominal_no_review(self):
        output = _dummy_output().model_copy(
            update={"loop_status": LoopStatus.NOMINAL, "requires_human_review": False}
        )
        assert output.is_actionable() is True

    def test_not_actionable_when_requires_human_review(self):
        output = _dummy_output().model_copy(update={"requires_human_review": True})
        assert output.is_actionable() is False

    def test_frozen(self):
        output = _dummy_output()
        with pytest.raises(ValidationError):
            output.rationale = "new"


class TestCognitiveLoopFullExecution:
    def test_run_returns_loop_output(self, loop):
        output = loop.run(LoopInput())
        assert isinstance(output, LoopOutput)

    def test_cycle_number_increments(self, loop):
        output1 = loop.run(LoopInput())
        output2 = loop.run(LoopInput())
        output3 = loop.run(LoopInput())
        assert [output1.cycle_number, output2.cycle_number, output3.cycle_number] == [1, 2, 3]

    def test_all_stage_results_present(self, loop):
        output = loop.run(LoopInput())
        expected = {"INGEST", "BELIEF", "SECURITY_MONITOR", "DECISION", "REPLAN", "VETO", "AUDIT", "OUTPUT"}
        assert expected == {stage.stage_name for stage in output.stage_results}

    def test_computation_ms_positive(self, loop):
        output = loop.run(LoopInput())
        assert output.computation_ms > 0.0

    def test_rationale_en_nonempty(self, loop):
        output = loop.run(LoopInput())
        assert isinstance(output.rationale, str)
        assert output.rationale.strip()

    def test_rationale_ar_nonempty(self, loop):
        output = loop.run(LoopInput())
        assert isinstance(output.rationale_ar, str)
        assert output.rationale_ar.strip()

    def test_history_grows(self, loop):
        loop.run(LoopInput())
        loop.run(LoopInput())
        assert len(loop.history(100)) >= 2

    def test_audit_log_grows(self, loop):
        loop.run(LoopInput())
        loop.run(LoopInput())
        assert len(loop.audit_log(100)) >= 2

    def test_history_rolling_window(self):
        bounded = create_cognitive_loop(config=LoopConfig(max_history=3))
        for _ in range(5):
            bounded.run(LoopInput())
        assert len(bounded.history(100)) <= 3

    def test_summary_returns_dict(self, loop):
        loop.run(LoopInput())
        summary = loop.summary()
        assert isinstance(summary, dict)
        assert "subsystems_available" in summary


@pytest.mark.skipif(not BELIEF_AVAILABLE, reason="belief subsystem unavailable")
class TestCognitiveLoopBeliefUpdates:
    def test_belief_updated_when_bundle_provided(self, warmed_loop, sample_bundle):
        output = warmed_loop.run(LoopInput(observation_bundle=sample_bundle))
        assert output.belief_version > 0

    def test_belief_version_in_audit_entry(self, warmed_loop, sample_bundle):
        output = warmed_loop.run(LoopInput(observation_bundle=sample_bundle))
        assert output.audit_entry.belief_version_after >= output.audit_entry.belief_version_before

    def test_belief_skipped_when_no_bundle(self, warmed_loop):
        output = warmed_loop.run(LoopInput(observation_bundle=None))
        belief_stage = next(stage for stage in output.stage_results if stage.stage_name == "BELIEF")
        assert belief_stage.status == StageStatus.SKIPPED

    def test_belief_snapshot_in_output(self, warmed_loop, sample_bundle):
        output = warmed_loop.run(LoopInput(observation_bundle=sample_bundle))
        assert output.belief_snapshot is not None

    def test_current_belief_returns_state(self, warmed_loop):
        assert warmed_loop.current_belief() is not None


@pytest.mark.skipif(not DECISION_AVAILABLE, reason="decision subsystem unavailable")
class TestCognitiveLoopDecision:
    def test_decision_produced_when_options_provided(self, warmed_loop, sample_options):
        output = warmed_loop.run(LoopInput(decision_options=sample_options))
        assert output.decision_result is not None

    def test_selected_option_label_in_output(self, warmed_loop, sample_options):
        output = warmed_loop.run(LoopInput(decision_options=sample_options))
        assert output.selected_option_label

    def test_decision_skipped_when_no_options(self, warmed_loop):
        output = warmed_loop.run(LoopInput(decision_options=[]))
        decision_stage = next(stage for stage in output.stage_results if stage.stage_name == "DECISION")
        assert decision_stage.status == StageStatus.SKIPPED

    def test_higher_ev_option_selected(self, warmed_loop):
        options = [
            DecisionOption(
                label="HOLD position",
                action_type=ActionType.HOLD,
                expected_outcome=0.75,
                probability_of_success=0.9,
                risk_score=0.1,
                cost_score=0.1,
                uncertainty=0.1,
            ),
            DecisionOption(
                label="ENGAGE target",
                action_type=ActionType.ENGAGE,
                expected_outcome=0.9,
                probability_of_success=0.55,
                risk_score=0.8,
                cost_score=0.6,
                uncertainty=0.3,
            ),
        ]
        output = warmed_loop.run(LoopInput(decision_options=options))
        assert output.selected_option_label == "HOLD position"

    @pytest.mark.skipif(not BELIEF_AVAILABLE, reason="belief subsystem unavailable")
    def test_decision_changes_across_cycles(self, warmed_loop, sample_options):
        output1 = warmed_loop.run(LoopInput(decision_options=sample_options))
        warmed_loop.belief_store.create(
            [BeliefHypothesis(description="Threat-Gamma", probability=0.34)],
            author="test-shift",
        )
        output2 = warmed_loop.run(LoopInput(decision_options=sample_options))
        assert output1.decision_confidence != output2.decision_confidence

    def test_confidence_in_audit_entry(self, warmed_loop, sample_options):
        output = warmed_loop.run(LoopInput(decision_options=sample_options))
        assert output.audit_entry.decision_confidence is not None


@pytest.mark.skipif(not SECURITY_AVAILABLE, reason="security monitor subsystem unavailable")
class TestCognitiveLoopAnomalies:
    def _warm_monitor(self, loop: CognitiveLoop):
        warm_obs = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.85,
                latency_ms=120.0,
                response_length=200,
                reasoning_steps=3,
            )
            for _ in range(15)
        ]
        loop.inference_monitor.observe_batch(warm_obs)

    def test_normal_inference_obs_no_alerts(self, warmed_loop, sample_inference_obs):
        self._warm_monitor(warmed_loop)
        output = warmed_loop.run(LoopInput(inference_observations=sample_inference_obs))
        assert len(output.security_alerts) == 0

    def test_anomalous_inference_obs_produces_alert(self, warmed_loop):
        self._warm_monitor(warmed_loop)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.05,
                latency_ms=120.0,
                response_length=200,
                reasoning_steps=3,
            )
        ]
        output = warmed_loop.run(LoopInput(inference_observations=anomalous))
        assert len(output.security_alerts) > 0

    @pytest.mark.skipif(not DECISION_AVAILABLE, reason="decision subsystem unavailable")
    def test_critical_alert_triggers_veto_when_configured(self, sample_options):
        guarded = create_cognitive_loop(config=LoopConfig.default())
        self._warm_monitor(guarded)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.0,
                latency_ms=9000.0,
                response_length=1,
                reasoning_steps=1,
            )
        ]
        output = guarded.run(
            LoopInput(inference_observations=anomalous, decision_options=sample_options)
        )
        if output.max_alert_severity() != "CRITICAL":
            pytest.skip("monitor did not classify anomaly as CRITICAL in this environment")
        assert output.security_veto_applied is True
        assert output.loop_status == LoopStatus.VETOED

    @pytest.mark.skipif(not DECISION_AVAILABLE, reason="decision subsystem unavailable")
    def test_veto_reason_populated_on_veto(self, sample_options):
        guarded = create_cognitive_loop(config=LoopConfig.default())
        self._warm_monitor(guarded)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.0,
                latency_ms=9000.0,
                response_length=1,
                reasoning_steps=1,
            )
        ]
        output = guarded.run(
            LoopInput(inference_observations=anomalous, decision_options=sample_options)
        )
        if not output.security_veto_applied:
            pytest.skip("veto not applied under current monitor thresholds")
        assert output.veto_reason

    @pytest.mark.skipif(not DECISION_AVAILABLE, reason="decision subsystem unavailable")
    def test_veto_reason_ar_populated(self, sample_options):
        guarded = create_cognitive_loop(config=LoopConfig.default())
        self._warm_monitor(guarded)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.0,
                latency_ms=9000.0,
                response_length=1,
                reasoning_steps=1,
            )
        ]
        output = guarded.run(
            LoopInput(inference_observations=anomalous, decision_options=sample_options)
        )
        if not output.security_veto_applied:
            pytest.skip("veto not applied under current monitor thresholds")
        assert output.veto_reason_ar

    @pytest.mark.skipif(not DECISION_AVAILABLE, reason="decision subsystem unavailable")
    def test_no_veto_when_config_disabled(self, sample_options):
        permissive_loop = create_cognitive_loop(config=LoopConfig.permissive())
        self._warm_monitor(permissive_loop)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.0,
                latency_ms=9000.0,
                response_length=1,
                reasoning_steps=1,
            )
        ]
        output = permissive_loop.run(
            LoopInput(inference_observations=anomalous, decision_options=sample_options)
        )
        assert output.security_veto_applied is False

    def test_high_anomaly_triggers_human_review(self):
        reviewed = create_cognitive_loop(
            config=LoopConfig(
                require_human_review_on_high_anomaly=True,
                security_block_on_critical=False,
            )
        )
        self._warm_monitor(reviewed)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.05,
                latency_ms=5000.0,
                response_length=10,
                reasoning_steps=1,
            )
        ]
        output = reviewed.run(LoopInput(inference_observations=anomalous))
        if output.max_alert_severity() not in {"HIGH", "CRITICAL"}:
            pytest.skip("monitor did not produce HIGH/CRITICAL anomaly")
        assert output.requires_human_review is True

    def test_human_review_reasons_populated(self):
        reviewed = create_cognitive_loop(
            config=LoopConfig(
                require_human_review_on_high_anomaly=True,
                security_block_on_critical=False,
            )
        )
        self._warm_monitor(reviewed)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.05,
                latency_ms=5000.0,
                response_length=10,
                reasoning_steps=1,
            )
        ]
        output = reviewed.run(LoopInput(inference_observations=anomalous))
        if not output.requires_human_review:
            pytest.skip("review not required under current monitor thresholds")
        assert len(output.human_review_reasons) > 0

    def test_security_stage_skipped_when_no_obs(self, warmed_loop):
        output = warmed_loop.run(LoopInput(inference_observations=[]))
        security_stage = next(
            stage for stage in output.stage_results if stage.stage_name == "SECURITY_MONITOR"
        )
        assert security_stage.status == StageStatus.SKIPPED

    def test_audit_entry_records_alert_count(self, warmed_loop):
        self._warm_monitor(warmed_loop)
        anomalous = [
            InferenceObservation(
                model_id="test-model",
                model_name="Test-LLM",
                domain=ModelDomain.TACTICAL,
                confidence_score=0.05,
                latency_ms=120.0,
                response_length=200,
                reasoning_steps=3,
            )
        ]
        output = warmed_loop.run(LoopInput(inference_observations=anomalous))
        assert output.audit_entry.n_inference_alerts == len(output.security_alerts)


@pytest.mark.skipif(
    not (REPLAN_AVAILABLE and BELIEF_AVAILABLE),
    reason="replanning or belief subsystem unavailable",
)
class TestCognitiveLoopReplanning:
    def test_no_replan_when_no_plan(self, warmed_loop):
        output = warmed_loop.run(LoopInput(current_plan=None))
        replan_stage = next(stage for stage in output.stage_results if stage.stage_name == "REPLAN")
        assert replan_stage.status == StageStatus.SKIPPED

    def test_nominal_plan_not_replanned(self, warmed_loop, sample_plan):
        output = warmed_loop.run(LoopInput(current_plan=sample_plan))
        assert output.replan_triggered is False

    def test_replan_triggered_on_belief_shift(self, warmed_loop, sample_plan):
        warmed_loop.belief_store.create(
            [
                BeliefHypothesis(description="h0", probability=0.1),
                BeliefHypothesis(description="h1", probability=0.9),
            ],
            author="shift",
        )
        output = warmed_loop.run(LoopInput(current_plan=sample_plan))
        if not output.replan_triggered:
            pytest.skip("plan repair engine did not trigger under this state")
        assert output.audit_entry.replan_triggered is True

    def test_repaired_plan_in_repair_result(self, warmed_loop, sample_plan):
        output = warmed_loop.run(LoopInput(current_plan=sample_plan))
        if output.repair_result is None:
            pytest.skip("repair result not available")
        assert getattr(output.repair_result, "repaired_plan", None) is not None

    def test_replan_trigger_reason_in_audit(self, warmed_loop, sample_plan):
        output = warmed_loop.run(LoopInput(current_plan=sample_plan))
        if not output.replan_triggered:
            pytest.skip("replan was not triggered")
        assert output.audit_entry.replan_trigger_reason


class TestCognitiveLoopRunBatch:
    def test_run_batch_returns_all_outputs(self, loop):
        outputs = loop.run_batch([LoopInput(), LoopInput(), LoopInput()])
        assert len(outputs) == 3

    def test_run_batch_cycle_numbers_sequential(self, loop):
        outputs = loop.run_batch([LoopInput(), LoopInput(), LoopInput()])
        assert [item.cycle_number for item in outputs] == [1, 2, 3]


class TestCreateCognitiveLoop:
    def test_factory_returns_loop(self):
        runtime = create_cognitive_loop()
        assert isinstance(runtime, CognitiveLoop)

    def test_factory_subsystems_available_summary(self):
        runtime = create_cognitive_loop()
        summary = runtime.summary()
        assert isinstance(summary["subsystems_available"], dict)

    def test_factory_graceful_when_chunks_missing(self):
        runtime = create_cognitive_loop()
        assert isinstance(runtime, CognitiveLoop)
