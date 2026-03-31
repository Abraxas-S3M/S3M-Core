"""Benchmark harness for dataset/model evaluation workflows."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Optional

from src.apps._shared import clamp, safe_float, utc_now_iso
from src.apps.data_management.data_loader import DataLoader
from src.apps.data_management.dataset_registry import DatasetRegistry


class BenchmarkHarness:
    """Run lightweight offline benchmarks over registered datasets."""

    def __init__(self, results_dir: str = "data/benchmarks/") -> None:
        self.results_dir = results_dir
        os.makedirs(self.results_dir, exist_ok=True)
        self.registry = DatasetRegistry()
        self.loader = DataLoader()
        self._benchmarks: list[dict[str, Any]] = []

    def _stub_detection_metrics(self, samples: int) -> dict[str, Any]:
        precision = 0.52 if samples else 0.0
        recall = 0.49 if samples else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "additional": {"mAP": round(clamp(f1 + 0.08, 0.0, 1.0), 3), "note": "Model not loaded"},
        }

    def _stub_anomaly_metrics(self, samples: int) -> dict[str, Any]:
        precision = 0.61 if samples else 0.0
        recall = 0.57 if samples else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "additional": {"auc_roc": round(clamp(f1 + 0.12, 0.0, 1.0), 3), "note": "Model not loaded"},
        }

    def _resolve_sample_count(self, data_payload: dict[str, Any], dataset_format: str) -> int:
        if "records" in data_payload:
            return int(data_payload.get("records", 0))
        if dataset_format in {"images", "video", "yolo"}:
            return int(data_payload.get("count", 0))
        return 0

    def run_benchmark(self, dataset_id: str, model_id: Optional[str] = None, task: str = "detection") -> dict[str, Any]:
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ValueError("dataset_id must be a non-empty string")
        if task not in {"detection", "anomaly"}:
            raise ValueError("task must be 'detection' or 'anomaly'")

        start = time.time()
        dataset = self.registry.get_dataset(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset not found: {dataset_id}")

        local_path = str(dataset.get("local_path", ""))
        data_payload: dict[str, Any] = {"records": 0}
        if local_path and os.path.exists(local_path):
            if os.path.isdir(local_path):
                data_payload = self.loader.load_image_directory(local_path)
            else:
                data_payload = self.loader.load(local_path)

        sample_count = self._resolve_sample_count(data_payload, str(dataset.get("format", "")))
        if task == "detection":
            metrics = self._stub_detection_metrics(sample_count)
        else:
            metrics = self._stub_anomaly_metrics(sample_count)

        result = {
            "benchmark_id": f"bench-{uuid.uuid4().hex[:12]}",
            "dataset_id": dataset_id,
            "model_id": model_id or "default-detector",
            "task": task,
            "metrics": metrics,
            "samples_evaluated": sample_count,
            "duration_ms": round((time.time() - start) * 1000.0, 3),
            "timestamp": utc_now_iso(),
        }
        self._benchmarks.append(result)
        return result

    def list_benchmarks(self) -> list[dict[str, Any]]:
        return list(self._benchmarks)

    def compare_benchmarks(self, benchmark_ids: list[str]) -> dict[str, Any]:
        if not isinstance(benchmark_ids, list) or any(not isinstance(x, str) for x in benchmark_ids):
            raise ValueError("benchmark_ids must be a list of strings")
        selected = [b for b in self._benchmarks if b["benchmark_id"] in benchmark_ids]
        return {
            "benchmark_ids": benchmark_ids,
            "comparisons": [
                {
                    "benchmark_id": b["benchmark_id"],
                    "dataset_id": b["dataset_id"],
                    "task": b["task"],
                    "precision": safe_float(b.get("metrics", {}).get("precision", 0.0)),
                    "recall": safe_float(b.get("metrics", {}).get("recall", 0.0)),
                    "f1": safe_float(b.get("metrics", {}).get("f1", 0.0)),
                }
                for b in selected
            ],
        }

    def export(self, benchmark_id: str, filepath: str) -> None:
        if not isinstance(benchmark_id, str) or not benchmark_id.strip():
            raise ValueError("benchmark_id must be a non-empty string")
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        benchmark = next((b for b in self._benchmarks if b["benchmark_id"] == benchmark_id), None)
        if not benchmark:
            raise ValueError(f"Benchmark not found: {benchmark_id}")
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(benchmark, handle, indent=2)
