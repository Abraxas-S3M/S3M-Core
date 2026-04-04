"""Unit tests for S3M adaptive quantization cascade behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from src.llm_core.adaptive_quantization_cascade import (
    AdaptiveQuantizationCascade,
    CascadeLevel,
)


def _weights() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(42)
    return {
        "layer0.weight": rng.normal(0.0, 0.75, size=(512, 512)).astype(np.float32),
        "layer1.weight": rng.normal(0.0, 0.65, size=(512, 512)).astype(np.float32),
    }


def test_load_build_cascade_profiles_and_simd_alignment() -> None:
    cascade = AdaptiveQuantizationCascade(model_id="s3m-aqc-test")
    state = cascade.load_and_build_cascade(_weights())

    assert state.current_level == CascadeLevel.INT8
    assert set(state.profiles.keys()) == {
        CascadeLevel.INT8,
        CascadeLevel.INT4,
        CascadeLevel.INT4_SPARSE,
        CascadeLevel.TERNARY,
    }

    for profile in state.profiles.values():
        assert profile.switch_cost_us < 1000.0
        for array in profile.lut_data.values():
            assert array.nbytes % 16 == 0

    status = cascade.get_cascade_status()
    assert status["cascade_overhead_ratio"] is not None
    assert status["cascade_overhead_ratio"] < 0.5


def test_mode_changes_are_thread_safe() -> None:
    cascade = AdaptiveQuantizationCascade(model_id="s3m-aqc-test")
    cascade.load_and_build_cascade(_weights())
    modes = [
        "full_edge",
        "cpu_constrained",
        "intermittent_link",
        "offline_survival",
    ] * 8

    with ThreadPoolExecutor(max_workers=8) as executor:
        levels = list(executor.map(cascade.on_mode_change, modes))

    assert all(isinstance(level, CascadeLevel) for level in levels)
    status = cascade.get_cascade_status()
    assert status["switch_count"] > 0
    assert status["current_level"] in {
        CascadeLevel.INT8.value,
        CascadeLevel.INT4.value,
        CascadeLevel.INT4_SPARSE.value,
        CascadeLevel.TERNARY.value,
    }


def test_get_active_weights_for_each_level() -> None:
    cascade = AdaptiveQuantizationCascade(model_id="s3m-aqc-test")
    base = _weights()
    cascade.load_and_build_cascade(base)

    mode_to_level = {
        "full_edge": CascadeLevel.INT8,
        "cpu_constrained": CascadeLevel.INT4,
        "intermittent_link": CascadeLevel.INT4_SPARSE,
        "offline_survival": CascadeLevel.TERNARY,
    }

    for mode, level in mode_to_level.items():
        cascade.on_mode_change(mode)
        assert cascade.state is not None
        assert cascade.state.current_level == level
        active = cascade.get_active_weights()
        for layer_name, layer_value in active.items():
            assert layer_name in base
            if level == CascadeLevel.TERNARY:
                assert set(layer_value.keys()) == {"dense", "sparse", "ternary"}
                assert layer_value["dense"].shape == base[layer_name].shape
                assert layer_value["sparse"].shape == base[layer_name].shape
                assert layer_value["ternary"].shape == base[layer_name].shape
            else:
                assert layer_value.shape == base[layer_name].shape


def test_quality_tracking_window_bounded_and_suggests_promotions() -> None:
    cascade = AdaptiveQuantizationCascade(model_id="s3m-aqc-test")
    cascade.load_and_build_cascade(_weights())
    cascade.on_mode_change("intermittent_link")

    suggestion = None
    for _ in range(65):
        suggestion = cascade.adapt_cascade_thresholds(0.2)

    assert cascade.state is not None
    assert len(cascade.state.quality_observations) == 50
    assert suggestion == CascadeLevel.INT4


def test_high_quality_can_suggest_demotion() -> None:
    cascade = AdaptiveQuantizationCascade(model_id="s3m-aqc-test")
    cascade.load_and_build_cascade(_weights())
    cascade.on_mode_change("cpu_constrained")

    suggestion = None
    for _ in range(25):
        suggestion = cascade.adapt_cascade_thresholds(0.99)

    assert suggestion == CascadeLevel.INT4_SPARSE


def test_infer_with_reference_quality_signal() -> None:
    cascade = AdaptiveQuantizationCascade(model_id="s3m-aqc-test")
    cascade.load_and_build_cascade(_weights())

    logits, _ = cascade.infer_with_quality_tracking(["alpha", "bravo", 3, 7])
    logits_2, quality = cascade.infer_with_quality_tracking(
        ["alpha", "bravo", 3, 7],
        reference_logits=logits,
    )

    assert logits_2.shape == logits.shape
    assert quality > 0.99
    assert cascade.state is not None
    assert len(cascade.state.quality_observations) >= 2
