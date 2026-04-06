"""Tests for shared cloud CPU training contracts used in tactical pipelines."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.training.cloud_cpu.contracts import (
    CheckpointMeta,
    CycleMetrics,
    DataClass,
    PromotionDecision,
    ScenarioManifest,
    TrainerState,
    TrainingExample,
)
from src.training.cloud_cpu.paths import TrainingTrack


def test_scenario_manifest_and_training_example_parse_enums() -> None:
    manifest = ScenarioManifest(
        scenario_id="scn-001",
        track="saudi_mod",
        data_class="command",
        prompt_count=10,
        version="1.0.0",
        checksum="sha256:abc",
    )
    example = TrainingExample(
        prompt="Summarize logistics status.",
        completion="Fuel stocks are at 82 percent with 48-hour sustainment margin.",
        domain_track=TrainingTrack.SAUDI_MOD,
        data_class=DataClass.RISK_READINESS,
        metadata={"source": "simulator"},
        weight=0.75,
    )

    assert manifest.track == TrainingTrack.SAUDI_MOD
    assert manifest.data_class == DataClass.COMMAND
    assert example.domain_track == TrainingTrack.SAUDI_MOD
    assert example.data_class == DataClass.RISK_READINESS


def test_training_example_rejects_negative_weight() -> None:
    with pytest.raises(ValidationError):
        TrainingExample(
            prompt="p",
            completion="c",
            domain_track="nato",
            data_class="command",
            weight=-0.1,
        )


def test_checkpoint_state_metrics_and_promotion_contracts() -> None:
    checkpoint = CheckpointMeta(
        checkpoint_id="ckpt-01",
        run_id="run-01",
        track=TrainingTrack.UKRAINE_MOD,
        step=50,
        epoch=2,
        loss=0.44,
        is_complete=True,
        is_promoted=False,
        sha256="deadbeef",
        eval_results={"overall": 0.68},
    )
    trainer_state = TrainerState(
        current_step=50,
        current_epoch=2,
        dataset_cursor={"ukraine_mod": 1200},
        last_eval={"overall": 0.68},
        last_promotion={},
        run_id="run-01",
    )
    metrics = CycleMetrics(
        cycle_id="cycle-01",
        step=50,
        epoch=2,
        track="ukraine_mod",
        samples_processed=256,
        loss=0.44,
        pseudo_label_acceptance_rate=0.71,
        eval_score=0.68,
        checkpoint_age_seconds=12.0,
    )
    decision = PromotionDecision(
        checkpoint_id="ckpt-01",
        track="ukraine_mod",
        passed=True,
        eval_scores={"overall": 0.68},
        thresholds={"overall": 0.65},
        promoted_at=datetime.now(timezone.utc),
        reason="All thresholds satisfied.",
    )

    assert checkpoint.track == TrainingTrack.UKRAINE_MOD
    assert trainer_state.run_id == "run-01"
    assert metrics.track == TrainingTrack.UKRAINE_MOD
    assert decision.passed is True


def test_cycle_metrics_rejects_out_of_range_acceptance_rate() -> None:
    with pytest.raises(ValidationError):
        CycleMetrics(
            cycle_id="cycle-02",
            step=1,
            epoch=0,
            track="shared",
            samples_processed=8,
            loss=0.9,
            pseudo_label_acceptance_rate=1.2,
            eval_score=0.3,
            checkpoint_age_seconds=2.0,
        )
