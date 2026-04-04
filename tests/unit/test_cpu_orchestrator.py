"""Integration tests for manifest-driven CPU orchestration."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.edge_runtime.cpu_orchestrator import CPUOrchestrator
from src.edge_runtime.degradation_controller import DegradationController
from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile
from src.edge_runtime.model_manifest import ModelManifest
from src.edge_runtime.model_planner import ExecutionDecision, ModelExecutionPlanner
from src.llm_core.engine_registry import EngineID
from src.llm_core.inference_engine import InferenceEngine, InferenceResult


def _write_manifest(manifest_dir: Path, model_id: str, adapter_allowed: bool = True) -> Path:
    model_file = manifest_dir / f"{model_id}.gguf"
    model_file.write_text("", encoding="utf-8")
    manifest_path = manifest_dir / f"{model_id}.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                f"model_id: {model_id}",
                f"model_name: {model_id}",
                "runtime_backend: llama_cpp",
                "training:",
                f"  adapter_tuning_allowed: {'true' if adapter_allowed else 'false'}",
                "thresholds:",
                "  max_prompt_chars: 4096",
                "  max_adapter_samples: 128",
                "variants:",
                "  - variant_tag: q4_k_m",
                "    runtime_format: gguf",
                "    precision: int4",
                f"    file_path: {model_file}",
                "    size_mb: 1200",
                "    min_ram_gb: 1.0",
                "    requires_gpu: false",
                "    max_context: 2048",
                "    estimated_tps_cpu: 12.0",
            ]
        ),
        encoding="utf-8",
    )
    return manifest_path


@pytest.fixture
def profile() -> NodeProfile:
    return NodeProfile(
        tier=HardwareTier.CPU_STANDARD,
        cpu_cores=8,
        cpu_arch="aarch64",
        ram_total_gb=16.0,
        ram_available_gb=12.0,
        disk_total_gb=128.0,
        disk_free_gb=64.0,
        gpu_detected=False,
        gpu_name=None,
        gpu_memory_mb=0,
        cuda_available=False,
        thermal_zone_c=48.0,
        power_source="mains",
        active_links=["eth0"],
    )


def test_manifest_and_planner_runtime_backend(tmp_path: Path, profile: NodeProfile) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_dir, "phi3-mini", adapter_allowed=True)

    manifest = ModelManifest.load("phi3-mini", manifest_dir=str(manifest_dir))
    assert manifest.model_id == "phi3-mini"

    controller = DegradationController(profile)
    planner = ModelExecutionPlanner(profile, controller)
    plan = planner.plan("phi3-mini", manifest=manifest)
    assert plan.decision == ExecutionDecision.RUN_LOCAL
    assert plan.runtime_format == "gguf"
    assert plan.backend == "llama_cpp"


def test_inference_engine_from_manifest_sets_backend(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_dir, "phi3-mini")

    engine = InferenceEngine.from_manifest("phi3-mini", manifest_dir=str(manifest_dir))
    assert engine.backend is not None
    assert engine.backend.backend_name == "llama_cpp"


def test_cpu_orchestrator_train_and_status(tmp_path: Path, profile: NodeProfile) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_dir, "phi3-mini", adapter_allowed=True)

    orchestrator = CPUOrchestrator(profile=profile, manifest_dir=str(manifest_dir))
    assert orchestrator.initialize() is True

    status = orchestrator.status()
    assert status["initialized"] is True
    assert "phi3-mini" in status["known_models"]

    training = orchestrator.train_adapter("phi3-mini", [{"prompt": "a", "response": "b"}])
    assert training.success is True


def test_cpu_orchestrator_evaluate_uses_harness(tmp_path: Path, profile: NodeProfile) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_dir, "phi3-mini", adapter_allowed=True)

    orchestrator = CPUOrchestrator(profile=profile, manifest_dir=str(manifest_dir))
    assert orchestrator.initialize() is True

    def fake_infer(model_id: str, prompt: str, **kwargs: object) -> InferenceResult:
        del kwargs
        return InferenceResult(
            engine_id=EngineID.PHI3,
            prompt=prompt,
            response=f"ok:{model_id}",
            tokens_generated=8,
            prompt_tokens=4,
            latency_ms=5.0,
            tokens_per_second=1600.0,
            model_name=model_id,
        )

    orchestrator.infer = fake_infer  # type: ignore[assignment]
    report = orchestrator.evaluate("phi3-mini", ["brief one", "brief two"])
    assert report.passed is True
    assert report.total_cases == 2
