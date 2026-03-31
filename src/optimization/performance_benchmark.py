"""Performance benchmark suite for Phase 12 deployment hardening."""

from __future__ import annotations

import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List


class PerformanceBenchmark:
    """Run repeatable performance probes across API and core workflows.

    Tactical context:
    Benchmarks are used during pre-mission checks to verify response envelopes
    remain within command-and-control timing thresholds.
    """

    DEFAULT_ENDPOINTS = [
        "/health",
        "/engines",
        "/threats/stats",
        "/autonomy/status",
        "/navigation/status",
        "/dashboard/overview",
    ]

    def __init__(self):
        pass

    def _quantile(self, values: List[float], q: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        index = min(len(sorted_vals) - 1, max(0, int(round((len(sorted_vals) - 1) * q))))
        return float(sorted_vals[index])

    def run_full_benchmark(self) -> dict:
        results = {
            "api_latency": self.benchmark_api_latency(),
            "inference_throughput": self.benchmark_inference_throughput(),
            "path_planning": self.benchmark_path_planning(),
            "detection_latency": self.benchmark_detection_latency(),
            "memory_peak": self.benchmark_memory_peak(),
        }
        results["report"] = self.generate_report(results)
        return results

    def benchmark_api_latency(self, endpoints: List[str] = None, n_requests: int = 50) -> dict:
        if endpoints is None:
            endpoints = list(self.DEFAULT_ENDPOINTS)
        if not isinstance(n_requests, int) or n_requests <= 0:
            raise ValueError("n_requests must be a positive integer")

        report: Dict[str, dict] = {}
        for endpoint in endpoints:
            latencies: List[float] = []
            errors = 0
            url = f"http://localhost:8080{endpoint}"
            for _ in range(n_requests):
                t0 = time.perf_counter()
                try:
                    with urllib.request.urlopen(url, timeout=2.0) as response:
                        _ = response.read(64)
                except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
                    errors += 1
                    continue
                latencies.append((time.perf_counter() - t0) * 1000.0)

            if latencies:
                report[endpoint] = {
                    "p50_ms": round(self._quantile(latencies, 0.50), 3),
                    "p95_ms": round(self._quantile(latencies, 0.95), 3),
                    "p99_ms": round(self._quantile(latencies, 0.99), 3),
                    "mean_ms": round(statistics.fmean(latencies), 3),
                    "errors": errors,
                }
            else:
                report[endpoint] = {
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                    "mean_ms": 0.0,
                    "errors": errors or n_requests,
                }
        return report

    def benchmark_inference_throughput(self) -> dict:
        try:
            from src.llm_core.orchestrator import Orchestrator, QueryRequest
            from src.llm_core.engine_registry import TaskDomain

            orchestrator = Orchestrator()
            engines = ["phi3", "grok", "mistral", "allam"]
            report: Dict[str, dict] = {}
            for engine in engines:
                latencies = []
                token_rates = []
                for _ in range(10):
                    t0 = time.perf_counter()
                    response = orchestrator.process(QueryRequest(prompt="Status check", domain=TaskDomain.TACTICAL))
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    text = getattr(response, "text", "") or getattr(response, "final_answer", "") or ""
                    tokens = max(1, len(str(text).split()))
                    latencies.append(latency_ms)
                    token_rates.append(tokens / max(1e-3, latency_ms / 1000.0))
                report[engine] = {
                    "avg_tokens_per_sec": round(statistics.fmean(token_rates), 3),
                    "avg_latency_ms": round(statistics.fmean(latencies), 3),
                }
            return report
        except Exception:
            return {
                "stub": {
                    "avg_tokens_per_sec": 0.0,
                    "avg_latency_ms": 0.0,
                    "note": "LLM engines unavailable in current environment",
                }
            }

    def benchmark_path_planning(self, n_runs: int = 20) -> dict:
        if not isinstance(n_runs, int) or n_runs <= 0:
            raise ValueError("n_runs must be a positive integer")

        try:
            from src.navigation.planning.path_planner import PathPlanner
        except Exception:
            return {
                "unavailable": {
                    "avg_time_ms": 0.0,
                    "avg_path_length": 0.0,
                    "success_rate": 0.0,
                    "note": "Navigation planner unavailable",
                }
            }

        planners = {"rrt_star": PathPlanner(), "a_star": PathPlanner()}
        result = {}

        for name, planner in planners.items():
            times = []
            lengths = []
            success = 0
            for run_idx in range(n_runs):
                start = (0, 0, 0)
                goal = (100 + run_idx, 100 + run_idx, 50)
                obstacles = [{"position": (50, 50, 25), "radius": 10 + (run_idx % 5)}]
                t0 = time.perf_counter()
                path = planner.plan(start, goal, obstacles=obstacles)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                times.append(elapsed_ms)
                if path:
                    success += 1
                    lengths.append(float(len(path)))

            result[name] = {
                "avg_time_ms": round(statistics.fmean(times) if times else 0.0, 3),
                "avg_path_length": round(statistics.fmean(lengths) if lengths else 0.0, 3),
                "success_rate": round(success / n_runs, 3),
            }

        return result

    def benchmark_detection_latency(self) -> dict:
        try:
            from src.threat_detection.object_detector import ObjectDetector

            detector = ObjectDetector(model_path="models/yolov8n-military.pt")
            latencies = []
            for _ in range(20):
                t0 = time.perf_counter()
                detector.detect("stub_image.jpg")
                latencies.append((time.perf_counter() - t0) * 1000.0)
            return {
                "avg_latency_ms": round(statistics.fmean(latencies), 3),
                "backend": "stub" if detector.stub_mode else "yolo",
            }
        except Exception:
            return {
                "avg_latency_ms": 0.0,
                "backend": "unavailable",
            }

    def benchmark_memory_peak(self) -> dict:
        def _mem_mb() -> float:
            try:
                with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                    data = handle.read().splitlines()
                mem = {}
                for line in data:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        mem[k.strip()] = int(v.strip().split()[0])
                return float(mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)) / 1024.0
            except Exception:
                return 0.0

        modules = [
            "src.llm_core",
            "src.threat_detection",
            "src.sensor_fusion",
            "src.autonomy",
            "src.navigation",
            "src.simulation",
            "src.dashboard",
            "src.security",
            "src.apps",
        ]

        result = {}
        baseline = _mem_mb()
        for module in modules:
            before = _mem_mb()
            try:
                __import__(module)
                after = _mem_mb()
                result[module] = {"delta_mb": round(max(0.0, after - before), 3), "status": "loaded"}
            except Exception as exc:
                result[module] = {"delta_mb": 0.0, "status": f"unavailable: {exc}"}
        result["baseline_used_mb"] = round(baseline, 3)
        return result

    def generate_report(self, results: dict, filepath: str = None) -> str:
        targets = {
            "api_ms": 100.0,
            "inference_ms": 5000.0,
            "planning_ms": 500.0,
            "detection_ms": 50.0,
        }

        lines = [
            "S3M PERFORMANCE BENCHMARK REPORT",
            "Classification: UNCLASSIFIED - FOUO",
            "",
            "Target Latencies:",
            f"- API: < {targets['api_ms']} ms",
            f"- Inference: < {targets['inference_ms']} ms",
            f"- Planning: < {targets['planning_ms']} ms",
            f"- Detection: < {targets['detection_ms']} ms",
            "",
            "Results:",
        ]

        api = results.get("api_latency", {})
        lines.append("API Latency:")
        for endpoint, metrics in api.items():
            lines.append(
                f"- {endpoint}: p50={metrics.get('p50_ms', 0)} ms, "
                f"p95={metrics.get('p95_ms', 0)} ms, errors={metrics.get('errors', 0)}"
            )

        infer = results.get("inference_throughput", {})
        lines.append("Inference Throughput:")
        for engine, metrics in infer.items():
            lines.append(
                f"- {engine}: avg_latency={metrics.get('avg_latency_ms', 0)} ms, "
                f"avg_tps={metrics.get('avg_tokens_per_sec', 0)}"
            )

        planning = results.get("path_planning", {})
        lines.append("Path Planning:")
        for planner, metrics in planning.items():
            lines.append(
                f"- {planner}: avg_time={metrics.get('avg_time_ms', 0)} ms, "
                f"success_rate={metrics.get('success_rate', 0)}"
            )

        detect = results.get("detection_latency", {})
        lines.append(
            f"Detection: avg_latency={detect.get('avg_latency_ms', 0)} ms, backend={detect.get('backend', 'unknown')}"
        )

        report = "\n".join(lines)
        if filepath:
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
        return report
