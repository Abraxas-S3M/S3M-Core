"""Unit tests for CPU-first model execution planner behavior."""

from src.edge_runtime.degradation_controller import DegradationController, OperatingMode
from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile
from src.edge_runtime.model_planner import (
    ExecutionDecision,
    ModelExecutionPlanner,
    Precision,
)


def _planner(
    *,
    mode: OperatingMode,
    ram_available_gb: float,
    gpu_detected: bool,
) -> ModelExecutionPlanner:
    profile = NodeProfile(
        tier=HardwareTier.TIER_1_BALANCED,
        ram_available_gb=ram_available_gb,
        gpu_detected=gpu_detected,
    )
    controller = DegradationController(initial_mode=mode)
    return ModelExecutionPlanner(profile=profile, controller=controller)


def test_rejects_unknown_model() -> None:
    planner = _planner(
        mode=OperatingMode.MODE_A_FULL_EDGE,
        ram_available_gb=8.0,
        gpu_detected=True,
    )

    plan = planner.plan("nonexistent-model", requested_tokens=256)

    assert plan.decision == ExecutionDecision.REJECT
    assert plan.variant is None
    assert plan.max_tokens == 0
    assert plan.max_context == 0
    assert "No variants registered" in plan.reason


def test_selects_smallest_feasible_variant_locally() -> None:
    planner = _planner(
        mode=OperatingMode.MODE_A_FULL_EDGE,
        ram_available_gb=6.0,
        gpu_detected=False,
    )

    plan = planner.plan("phi3-medium", requested_tokens=1024)

    assert plan.decision == ExecutionDecision.RUN_LOCAL
    assert plan.variant is not None
    assert plan.variant.variant_tag == "q4_k_m"
    assert plan.precision == Precision.INT4
    assert plan.max_tokens == 1024
    assert plan.max_context == 4096
    assert plan.max_batch == 4


def test_defers_to_peer_when_no_local_variant_and_peer_allowed() -> None:
    planner = _planner(
        mode=OperatingMode.MODE_C_NETWORK_AUGMENTED,
        ram_available_gb=4.0,
        gpu_detected=False,
    )

    plan = planner.plan("grok1", requested_tokens=700)

    assert plan.decision == ExecutionDecision.DEFER_TO_PEER
    assert plan.variant is None
    assert plan.precision == Precision.INT4
    assert plan.max_tokens == 700
    assert "deferring to peer" in plan.reason


def test_summarizes_when_no_local_variant_and_no_peer_allowed() -> None:
    planner = _planner(
        mode=OperatingMode.MODE_D_OFFLINE_SURVIVAL,
        ram_available_gb=4.0,
        gpu_detected=False,
    )

    plan = planner.plan("grok1", requested_tokens=700)

    assert plan.decision == ExecutionDecision.SUMMARIZE_INSTEAD
    assert plan.variant is None
    assert plan.precision == Precision.INT4
    assert plan.max_tokens == 128
    assert "summarization" in plan.reason


def test_mode_b_limits_context_tokens_and_batch() -> None:
    planner = _planner(
        mode=OperatingMode.MODE_B_CPU_CONSTRAINED,
        ram_available_gb=8.0,
        gpu_detected=True,
    )

    plan = planner.plan("mixtral-8x7b", requested_tokens=5000)

    assert plan.decision == ExecutionDecision.RUN_LOCAL
    assert plan.variant is not None
    assert plan.variant.variant_tag == "q4_k_m"
    assert plan.max_tokens == 512
    assert plan.max_context == 2048
    assert plan.max_batch == 1


def test_mode_d_sets_survival_token_ceiling() -> None:
    planner = _planner(
        mode=OperatingMode.MODE_D_OFFLINE_SURVIVAL,
        ram_available_gb=8.0,
        gpu_detected=True,
    )

    plan = planner.plan("mixtral-8x7b", requested_tokens=2000)

    assert plan.decision == ExecutionDecision.RUN_LOCAL
    assert plan.variant is not None
    assert plan.max_tokens == 256
    assert plan.max_context == 2048
    assert plan.max_batch == 1


def test_to_dict_contains_selected_variant_fields() -> None:
    planner = _planner(
        mode=OperatingMode.MODE_A_FULL_EDGE,
        ram_available_gb=8.0,
        gpu_detected=True,
    )

    plan = planner.plan("phi3-medium", requested_tokens=256)
    serialized = plan.to_dict()

    assert serialized["decision"] == "run_local"
    assert serialized["variant"] == "q4_k_m"
    assert serialized["model_id"] == "phi3-medium"
    assert serialized["precision"] == "int4"
    assert serialized["max_tokens"] == 256
