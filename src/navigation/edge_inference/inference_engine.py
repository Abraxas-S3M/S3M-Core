"""Edge inference engine with backend selection for Jetson deployments."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from src.navigation.models import InferenceResult

LOGGER = logging.getLogger(__name__)


class EdgeInferenceEngine:
    """Runs model inference on best available local backend.

    Military context:
    Local edge inference removes network dependency so threat recognition and
    control decisions continue under communications-denied operations.
    """

    def __init__(self) -> None:
        self.backend_name = "none"
        self._backend_details: Dict[str, bool] = {}
        self.loaded_models: Dict[str, Dict[str, Any]] = {}
        self._latency_stats: Dict[str, List[float]] = {}
        self._detect_backends()

    def _detect_backends(self) -> None:
        trt_ok = False
        ort_ok = False
        torch_ok = False
        try:
            import tensorrt  # type: ignore  # pragma: no cover

            _ = tensorrt
            trt_ok = True
        except Exception:
            trt_ok = False
        try:
            import onnxruntime  # type: ignore  # pragma: no cover

            _ = onnxruntime
            ort_ok = True
        except Exception:
            ort_ok = False
        try:
            import torch  # type: ignore  # pragma: no cover

            _ = torch
            torch_ok = True
        except Exception:
            torch_ok = False

        self._backend_details = {"tensorrt": trt_ok, "onnxruntime": ort_ok, "torch": torch_ok}
        if trt_ok:
            self.backend_name = "tensorrt"
        elif ort_ok:
            self.backend_name = "onnxruntime"
        elif torch_ok:
            self.backend_name = "pytorch"
        else:
            self.backend_name = "none"

    def _new_model_id(self) -> str:
        return f"model-{uuid.uuid4().hex[:12]}"

    def load_model(self, model_path: str, model_id: Optional[str] = None) -> str:
        if not isinstance(model_path, str) or not model_path.strip():
            raise ValueError("model_path must be a non-empty string")
        if not os.path.exists(model_path):
            raise FileNotFoundError(model_path)
        resolved_id = model_id or self._new_model_id()
        ext = os.path.splitext(model_path)[1].lower()
        runtime_obj: Any = None
        runtime_backend = self.backend_name

        try:
            if self.backend_name == "tensorrt" and ext in {".engine", ".trt"}:
                import tensorrt as trt  # type: ignore

                with open(model_path, "rb") as handle:
                    raw = handle.read()
                logger = trt.Logger(trt.Logger.WARNING)
                runtime = trt.Runtime(logger)
                runtime_obj = runtime.deserialize_cuda_engine(raw)
            elif self.backend_name == "onnxruntime" and ext == ".onnx":
                import onnxruntime as ort  # type: ignore

                runtime_obj = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            elif self.backend_name == "pytorch" and ext in {".pt", ".pth"}:
                import torch  # type: ignore

                runtime_obj = torch.load(model_path, map_location="cpu")
                if hasattr(runtime_obj, "eval"):
                    runtime_obj.eval()
            else:
                runtime_backend = "stub"
        except Exception as exc:
            LOGGER.warning("Model load failed, entering stub mode: %s", exc)
            runtime_backend = "stub"
            runtime_obj = None

        self.loaded_models[resolved_id] = {
            "path": model_path,
            "object": runtime_obj,
            "backend": runtime_backend,
            "size_mb": os.path.getsize(model_path) / (1024.0 * 1024.0),
        }
        self._latency_stats[resolved_id] = []
        return resolved_id

    def _coerce_input(self, input_data: Any) -> Any:
        try:
            import numpy as np  # type: ignore

            if isinstance(input_data, np.ndarray):
                return input_data
            if isinstance(input_data, list):
                return np.asarray(input_data, dtype=np.float32)
        except Exception:
            pass
        return input_data

    def _stub_result(self, model_id: str, latency_ms: float) -> InferenceResult:
        return InferenceResult(
            model_id=model_id,
            output={
                "warning": "No ML runtime backend available; returning stub result",
                "backend": "stub",
            },
            latency_ms=latency_ms,
        )

    def predict(self, model_id: str, input_data: Any) -> InferenceResult:
        if model_id not in self.loaded_models:
            raise ValueError(f"Model not loaded: {model_id}")
        spec = self.loaded_models[model_id]
        backend = spec["backend"]
        runtime_obj = spec["object"]
        data = self._coerce_input(input_data)
        t0 = time.perf_counter()
        output: Any = None
        try:
            if backend == "onnxruntime" and runtime_obj is not None:
                input_name = runtime_obj.get_inputs()[0].name
                output = runtime_obj.run(None, {input_name: data})
            elif backend == "pytorch" and runtime_obj is not None:
                try:
                    import torch  # type: ignore

                    if not isinstance(data, torch.Tensor):
                        data = torch.as_tensor(data)
                    with torch.no_grad():
                        output = runtime_obj(data)
                    if hasattr(output, "detach"):
                        output = output.detach().cpu().tolist()
                except Exception:
                    output = None
            elif backend == "tensorrt" and runtime_obj is not None:
                # Non-CUDA dev environments cannot execute TensorRT contexts reliably.
                output = {"warning": "TensorRT engine loaded but execution stubbed in this environment"}
            else:
                output = None
        except Exception as exc:
            LOGGER.warning("Prediction failed for model %s: %s", model_id, exc)
            output = None
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self._latency_stats.setdefault(model_id, []).append(latency_ms)
        if len(self._latency_stats[model_id]) > 200:
            self._latency_stats[model_id] = self._latency_stats[model_id][-200:]
        if output is None:
            return self._stub_result(model_id, latency_ms)
        return InferenceResult(model_id=model_id, output=output, latency_ms=latency_ms)

    def predict_batch(self, model_id: str, batch_data: List[Any]) -> List[InferenceResult]:
        if not isinstance(batch_data, list):
            raise ValueError("batch_data must be a list")
        return [self.predict(model_id, item) for item in batch_data]

    def unload_model(self, model_id: str) -> None:
        self.loaded_models.pop(model_id, None)
        self._latency_stats.pop(model_id, None)

    def list_models(self) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for model_id, spec in self.loaded_models.items():
            latencies = self._latency_stats.get(model_id, [])
            avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
            payload.append(
                {
                    "model_id": model_id,
                    "path": spec["path"],
                    "backend": spec["backend"],
                    "size_mb": spec["size_mb"],
                    "avg_latency_ms": avg_latency,
                }
            )
        return payload

    def get_memory_usage(self) -> float:
        total = 0.0
        for spec in self.loaded_models.values():
            total += float(spec.get("size_mb", 0.0))
        return total

    def health_check(self) -> Dict[str, Any]:
        all_latencies = [lat for values in self._latency_stats.values() for lat in values]
        avg_latency = (sum(all_latencies) / len(all_latencies)) if all_latencies else 0.0
        return {
            "backend": self.backend_name,
            "backends_available": dict(self._backend_details),
            "models_loaded": len(self.loaded_models),
            "total_memory_mb": self.get_memory_usage(),
            "avg_latency_ms": avg_latency,
        }
