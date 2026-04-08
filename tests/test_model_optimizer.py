import pytest

from src.llm_core.engine_registry import EngineID
from src.llm_core.model_optimizer import (
    HardwareProfile,
    LoadCategory,
    ModelOptimizer as LLMModelOptimizer,
    RuntimeProfile,
)
from src.navigation.edge_inference.model_optimizer import (
    ModelOptimizer as EdgeModelOptimizer,
)


class TestModelOptimizer:
    """Test llm_core resource allocation and preload planning."""

    @pytest.fixture
    def optimizer(self):
        return LLMModelOptimizer()

    def test_estimate_total_memory(self, optimizer):
        """Total memory calculation."""
        all_engines = list(EngineID)
        total = optimizer.estimate_total_memory(all_engines)
        # Phi-3 Medium: 10 + Grok-1: 85 + Mixtral: 28 + ALLaM: 5 = 128
        assert 128.0 <= total <= 130.0

    def test_allocate_edge_16gb(self, optimizer):
        """16GB edge device can fit Phi-3 only by profile policy."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_16GB.value)
        assert plan.is_feasible()
        assert EngineID.PHI3_MEDIUM in plan.allocated_engines
        assert len(plan.allocated_engines) == 1

    def test_allocate_edge_32gb(self, optimizer):
        """32GB edge device fits Phi-3 + 1 other by profile policy."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_32GB.value)
        assert plan.is_feasible()
        assert EngineID.PHI3_MEDIUM in plan.allocated_engines
        assert len(plan.allocated_engines) == 2

    def test_allocate_edge_64gb(self, optimizer):
        """64GB edge device fits 3 engines by profile policy."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_64GB.value)
        assert plan.is_feasible()
        assert len(plan.allocated_engines) >= 3

    def test_allocate_server_128gb(self, optimizer):
        """128GB server fits all 4 engines."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.SERVER_128GB.value)
        assert plan.is_feasible()
        assert len(plan.allocated_engines) == 4

    def test_validate_budget_fits(self, optimizer):
        """Validation passes for engines that fit."""
        budget = optimizer.validate_budget(
            [EngineID.PHI3_MEDIUM, EngineID.MIXTRAL],
            available_memory_gb=40.0,
        )
        assert budget.fits
        assert budget.overage_gb == 0.0

    def test_validate_budget_exceeds(self, optimizer):
        """Validation fails for budget overflow."""
        budget = optimizer.validate_budget(
            list(EngineID),  # All 4 engines
            available_memory_gb=16.0,  # Only 16GB
        )
        assert not budget.fits
        assert budget.overage_gb > 0.0

    def test_preload_plan_always_loaded(self, optimizer):
        """Phi-3 is always in startup_engines."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_64GB.value)
        preload = optimizer.plan_preload(plan)
        assert EngineID.PHI3_MEDIUM in preload.startup_engines

    def test_preload_plan_opportunistic(self, optimizer):
        """Some engines marked opportunistic."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_64GB.value)
        preload = optimizer.plan_preload(plan)
        assert len(preload.opportunistic_engines) > 0

    def test_runtime_profile_edge_minimal(self, optimizer):
        """16GB -> EDGE_MINIMAL."""
        profile = optimizer.recommend_runtime_profile(16.0)
        assert profile == RuntimeProfile.EDGE_MINIMAL.value

    def test_runtime_profile_server_full(self, optimizer):
        """128GB -> SERVER_FULL."""
        profile = optimizer.recommend_runtime_profile(128.0)
        assert profile == RuntimeProfile.SERVER_FULL.value

    def test_startup_time_estimation(self, optimizer):
        """Startup time is positive and reasonable."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_64GB.value)
        preload = optimizer.plan_preload(plan)
        assert preload.estimated_startup_time_ms > 0
        assert preload.estimated_startup_time_ms < 10000  # Less than 10s

    def test_utilization_percentage(self, optimizer):
        """Utilization is reasonable."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_64GB.value)
        assert 0.0 <= plan.utilization_percent <= 1.0

    def test_consensus_available_on_server(self, optimizer):
        """Consensus available on 64GB+ systems."""
        plan_64gb = optimizer.allocate_for_hardware(HardwareProfile.EDGE_64GB.value)
        assert plan_64gb.consensus_available

        plan_128gb = optimizer.allocate_for_hardware(HardwareProfile.SERVER_128GB.value)
        assert plan_128gb.consensus_available

    def test_consensus_unavailable_on_edge(self, optimizer):
        """Consensus unavailable on 16GB/32GB."""
        plan_16gb = optimizer.allocate_for_hardware(HardwareProfile.EDGE_16GB.value)
        assert not plan_16gb.consensus_available

        plan_32gb = optimizer.allocate_for_hardware(HardwareProfile.EDGE_32GB.value)
        assert not plan_32gb.consensus_available

    def test_load_plan_has_all_categories(self, optimizer):
        """Load plan marks unallocated engines as NEVER_LOADED."""
        plan = optimizer.allocate_for_hardware(HardwareProfile.EDGE_16GB.value)
        assert plan.load_plan[EngineID.PHI3_MEDIUM] == LoadCategory.ALWAYS_LOADED
        assert any(cat == LoadCategory.NEVER_LOADED for cat in plan.load_plan.values())


def test_initialization_creates_output_directory(tmp_path):
    """Existing navigation optimizer behavior remains covered."""
    out = tmp_path / "optimized"
    EdgeModelOptimizer(output_dir=str(out))
    assert out.exists()


def test_list_optimized_models_empty(tmp_path):
    """Navigation optimizer returns no models on empty folder."""
    optimizer = EdgeModelOptimizer(output_dir=str(tmp_path))
    assert optimizer.list_optimized_models() == []


def test_estimate_memory_positive(tmp_path):
    """Navigation optimizer reports non-zero memory estimate."""
    dummy = tmp_path / "model.bin"
    dummy.write_bytes(b"\x00" * 256)
    optimizer = EdgeModelOptimizer(output_dir=str(tmp_path / "out"))
    assert optimizer.estimate_memory(str(dummy)) > 0


def test_benchmark_runs_without_loaded_models(tmp_path):
    """Navigation optimizer benchmark remains operable offline."""
    dummy = tmp_path / "model.onnx"
    dummy.write_bytes(b"\x00" * 512)
    optimizer = EdgeModelOptimizer(output_dir=str(tmp_path / "out"))
    result = optimizer.benchmark(str(dummy), n_iterations=5)
    assert result["avg_latency_ms"] >= 0
    assert result["throughput_fps"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
