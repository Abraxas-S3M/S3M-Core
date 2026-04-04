"""Unit tests for CPU training precision policy selection."""

from __future__ import annotations

from src.edge_runtime.hardware_profiler import HardwareTier, NodeProfile
from src.training.cpu_adaptation.precision_policy import PrecisionPolicyEngine, TrainingPrecision


def _profile(**overrides: object) -> NodeProfile:
    base = {
        "tier": HardwareTier.CPU_STANDARD,
        "cpu_cores": 12,
        "cpu_arch": "x86_64",
        "ram_total_gb": 32.0,
        "ram_available_gb": 24.0,
        "disk_total_gb": 512.0,
        "disk_free_gb": 256.0,
        "gpu_detected": False,
        "gpu_name": None,
        "gpu_memory_mb": 0,
        "cuda_available": False,
        "thermal_zone_c": 45.0,
        "power_source": "mains",
        "active_links": ["eth0"],
        "avx2_supported": False,
        "avx512_supported": False,
        "avx512_bf16_supported": False,
        "avx512_vnni_supported": False,
        "arm_neon_supported": False,
        "arm_sve_supported": False,
        "numa_node_count": 1,
        "simd_register_width_bits": 128,
    }
    base.update(overrides)
    return NodeProfile(**base)


def test_select_precision_prefers_bf16_on_avx512_bf16() -> None:
    profile = _profile(
        avx2_supported=True,
        avx512_supported=True,
        avx512_bf16_supported=True,
        simd_register_width_bits=512,
    )
    engine = PrecisionPolicyEngine(profile)
    config = engine.select_precision("adapter_tuning")

    assert config.training_precision is TrainingPrecision.BF16_MIXED
    assert config.forward_dtype == "bfloat16"
    assert config.master_weight_dtype == "float32"
    assert config.torch_compile_backend == "ipex"
    assert config.optimal_num_threads == 11


def test_select_precision_qat_enables_int4_clipping_and_numa_tuning() -> None:
    profile = _profile(cpu_cores=16, ram_available_gb=8.0, numa_node_count=2)
    engine = PrecisionPolicyEngine(profile)
    config = engine.select_precision("qat_4bit")
    env = engine.get_environment_recommendations()

    assert config.training_precision is TrainingPrecision.QAT_INT4
    assert config.forward_dtype == "int4"
    assert config.use_gradient_clipping is True
    assert config.gradient_clip_norm == 0.5
    assert config.use_tanh_soft_clipping is True
    assert config.numa_aware_threading is True
    assert config.optimal_num_threads == 7
    assert env["OMP_NUM_THREADS"] == "7"
    assert env["MALLOC_CONF"] != ""
    assert env["LD_PRELOAD"] != ""


def test_unknown_task_falls_back_to_adapter_policy() -> None:
    profile = _profile(cpu_arch="arm64", arm_neon_supported=True, simd_register_width_bits=128)
    engine = PrecisionPolicyEngine(profile)
    config = engine.select_precision("unexpected-task")
    autocast_cfg = engine.get_torch_autocast_config()

    assert config.training_precision is TrainingPrecision.FP32
    assert "FP32" in config.reason or "fp32" in config.reason.lower()
    assert autocast_cfg["enabled"] is False
    assert autocast_cfg["dtype"] == "float32"

