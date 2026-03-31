#!/usr/bin/env python3
"""S3M Phase 8 demo: edge inference and Jetson telemetry workflow."""

from __future__ import annotations

import os
import tempfile

from src.navigation.edge_inference.edge_llm_runner import EdgeLLMRunner
from src.navigation.edge_inference.inference_engine import EdgeInferenceEngine
from src.navigation.edge_inference.jetson_monitor import JetsonMonitor
from src.navigation.edge_inference.model_optimizer import ModelOptimizer


def _create_dummy_model_file() -> str:
    fd, path = tempfile.mkstemp(suffix=".onnx", prefix="s3m_dummy_")
    os.close(fd)
    with open(path, "wb") as handle:
        handle.write(os.urandom(4096))
    return path


def main() -> None:
    print("=" * 70)
    print("S3M Phase 8 Demo — Edge Inference Pipeline")
    print("Mission context: maintain local AI inference under denied comms links.")
    print("=" * 70)

    monitor = JetsonMonitor()
    caps = monitor.get_cuda_info()
    stats = monitor.get_stats()
    print("\n[1] Jetson capabilities")
    print(f"  Simulated: {monitor.is_simulated()}")
    print(f"  CUDA: {caps.get('cuda_version')}")
    print(f"  TensorRT available: {caps.get('tensorrt_available')}")
    print(f"  ONNX Runtime available: {caps.get('onnxruntime_available')}")
    print(f"  Thermal throttling: {stats.is_thermal_throttling()}")

    engine = EdgeInferenceEngine()
    print("\n[2] Inference engine backend")
    print(f"  Selected backend: {engine.backend_name}")
    print(f"  Backend details: {engine.health_check()['backends_available']}")

    dummy_model = _create_dummy_model_file()
    try:
        print("\n[3] Benchmarking dummy model")
        optimizer = ModelOptimizer(output_dir="models/optimized/")
        benchmark = optimizer.benchmark(dummy_model, n_iterations=10)
        print(f"  Avg latency: {benchmark['avg_latency_ms']:.2f} ms")
        print(f"  Throughput: {benchmark['throughput_fps']:.2f} FPS")
        print(f"  Memory estimate: {benchmark['memory_mb']:.2f} MB")

        print("\n[4] Edge LLM status")
        llm = EdgeLLMRunner()
        llm_health = llm.health_check()
        print(f"  Backend: {llm_health['backend']}")
        print(f"  Model loaded: {llm_health['model_loaded']}")
        print(f"  Model path: {llm_health['model_path']}")

        print("\n[5] Memory budget recommendation")
        print(f"  Recommended budget: {monitor.recommend_model_budget():.2f} MB")

        print("\n[6] Model optimization pipeline")
        print("  Step A: Detect source format (.pt/.onnx/.engine)")
        print("  Step B: Convert PyTorch -> ONNX when torch available")
        print("  Step C: Convert ONNX -> TensorRT when TensorRT available")
        print("  Step D: Benchmark optimized artifact with dummy inference loop")
        optimized = optimizer.optimize(dummy_model)
        print(f"  Produced artifact: {optimized.file_path}")
        print(f"  Framework: {optimized.framework}")
        print(f"  Avg latency: {optimized.avg_latency_ms:.2f} ms")
    finally:
        if os.path.exists(dummy_model):
            os.remove(dummy_model)

    print("\nDemo complete.")


if __name__ == "__main__":
    main()
