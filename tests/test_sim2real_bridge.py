"""Tests for S3M Sim2Real transfer bridge."""

import random

from src.simulation.sim2real.domain_randomizer import DomainRandomizer
from src.simulation.sim2real.transfer_bridge import TransferBridge


def test_domain_randomizer_applies_noise() -> None:
    rand = DomainRandomizer(seed=42)
    sample = {"x": 100.0, "y": 50.0, "z": 10.0, "sensor_reading": 0.85}
    result = rand.randomize(sample)
    assert result.randomized_data != sample
    assert len(result.applied_randomizations) > 0
    assert result.weather in ["clear", "fog", "rain", "dust", "night"]
    assert result.terrain in ["desert", "urban", "maritime", "mountain", "forest"]


def test_domain_randomizer_preserves_non_numeric() -> None:
    rand = DomainRandomizer(seed=7)
    sample = {"label": "tank", "x": 10.0}
    result = rand.randomize(sample)
    assert result.randomized_data["label"] == "tank"


def test_transfer_bridge_gap_assessment() -> None:
    bridge = TransferBridge(gap_threshold=0.3)
    rng = random.Random(42)

    sim_preds = [rng.random() for _ in range(100)]
    sim_labels = [1.0 if p > 0.5 else 0.0 for p in sim_preds]
    bridge.record_sim_performance(sim_preds, sim_labels)

    real_preds = [min(1.0, max(0.0, p + rng.gauss(0, 0.15))) for p in sim_preds]
    real_labels = sim_labels
    bridge.record_real_performance(real_preds, real_labels)

    gap = bridge.assess_transfer_gap()
    assert gap.metrics is not None
    assert gap.overall_gap_score >= 0
    assert len(gap.recommendations) > 0
    assert len(gap.recommendations_ar) > 0


def test_transfer_bridge_good_transfer() -> None:
    bridge = TransferBridge(gap_threshold=0.5)
    preds = [0.9, 0.8, 0.1, 0.2, 0.7]
    labels = [1.0, 1.0, 0.0, 0.0, 1.0]
    bridge.record_sim_performance(preds, labels)
    bridge.record_real_performance(preds, labels)
    gap = bridge.assess_transfer_gap()
    assert gap.ready_for_deployment is True
    assert gap.overall_gap_score < 0.5
