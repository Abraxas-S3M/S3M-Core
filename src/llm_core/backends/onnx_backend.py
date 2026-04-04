"""
S3M ONNX Runtime Backend
Enables air-gapped CPU inference for tactical language workflows using ONNX graphs.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any
import logging

import numpy as np

from .base_backend import InferenceBackend

try:
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_AVAILABLE = False

try:
    from transformers import AutoTokenizer

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    AutoTokenizer = None
    TRANSFORMERS_AVAILABLE = False

logger = logging.getLogger("s3m.backends.onnx")


class OnnxBackend(InferenceBackend):
    """Inference backend that wraps onnxruntime.InferenceSession."""

    def __init__(self, model_path: str, config: dict[str, Any]) -> None:
        super().__init__(model_path=model_path, config=config)
        self.execution_providers = list(config.get("execution_providers", ["CPUExecutionProvider"]))
        self._session: Any = None
        self._tokenizer: Any = None

    @property
    def backend_name(self) -> str:
        return "onnx"

    def load(self) -> bool:
        if not ONNX_AVAILABLE or ort is None:
            logger.warning("onnxruntime is not installed; ONNX backend unavailable")
            return False
        if not TRANSFORMERS_AVAILABLE or AutoTokenizer is None:
            logger.warning("transformers is not installed; tokenizer load unavailable")
            return False

        model_file = Path(self.model_path)
        if not model_file.exists():
            logger.error("ONNX model file not found: %s", model_file)
            return False

        tokenizer_path = self.config.get("tokenizer_path") or str(model_file.parent)

        try:
            sess_options = ort.SessionOptions()
            if self.config.get("inter_op_num_threads") is not None:
                sess_options.inter_op_num_threads = int(self.config["inter_op_num_threads"])
            if self.config.get("intra_op_num_threads") is not None:
                sess_options.intra_op_num_threads = int(self.config["intra_op_num_threads"])

            self._session = ort.InferenceSession(
                str(model_file),
                sess_options=sess_options,
                providers=self.execution_providers,
            )
            self._tokenizer = AutoTokenizer.from_pretrained(
                tokenizer_path,
                local_files_only=True,
            )
            self._loaded = True
            return True
        except Exception:
            logger.exception("Failed to initialize ONNX backend")
            self._loaded = False
            return False

    def unload(self) -> None:
        self._session = None
        self._tokenizer = None
        self._loaded = False

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        del temperature, top_p  # ONNX graph execution is model-export dependent.

        if not self._loaded or self._session is None or self._tokenizer is None:
            return self._error_result("Model not loaded")

        try:
            start = perf_counter()
            encoded = self._tokenizer(prompt, return_tensors="np")
            generated_ids = encoded["input_ids"].astype(np.int64)
            attention_mask = encoded.get("attention_mask")
            if attention_mask is not None:
                attention_mask = attention_mask.astype(np.int64)

            prompt_tokens = int(generated_ids.shape[-1])
            initial_tokens = prompt_tokens

            for _ in range(max_tokens):
                model_inputs = self._build_model_inputs(generated_ids, attention_mask)
                outputs = self._session.run(None, model_inputs)
                next_token = self._extract_next_token_id(outputs[0])
                if next_token is None:
                    break

                generated_ids = np.concatenate(
                    [generated_ids, np.array([[next_token]], dtype=np.int64)],
                    axis=-1,
                )
                if attention_mask is not None:
                    attention_mask = np.concatenate(
                        [attention_mask, np.ones((1, 1), dtype=np.int64)],
                        axis=-1,
                    )

                if stop:
                    partial_text = self._tokenizer.decode(
                        generated_ids[0, initial_tokens:],
                        skip_special_tokens=True,
                    )
                    if any(s in partial_text for s in stop):
                        break

            response_ids = generated_ids[0, initial_tokens:]
            response_text = self._tokenizer.decode(response_ids, skip_special_tokens=True).strip()
            if stop:
                for marker in stop:
                    if marker and marker in response_text:
                        response_text = response_text.split(marker, 1)[0].rstrip()

            latency_ms = (perf_counter() - start) * 1000.0
            tokens_generated = int(max(0, generated_ids.shape[-1] - initial_tokens))
            tokens_per_second = (tokens_generated / (latency_ms / 1000.0)) if latency_ms > 0 else 0.0

            return {
                "response": response_text,
                "tokens_generated": tokens_generated,
                "prompt_tokens": prompt_tokens,
                "latency_ms": latency_ms,
                "tokens_per_second": tokens_per_second,
            }
        except Exception:
            logger.exception("ONNX generation failed")
            return self._error_result("Inference failed")

    def health_check(self) -> dict[str, Any]:
        providers: list[str] = self.execution_providers
        if self._session is not None:
            try:
                providers = list(self._session.get_providers())
            except Exception:
                logger.debug("Could not query active ONNX providers", exc_info=True)

        return {
            "backend": self.backend_name,
            "loaded": self._loaded,
            "onnx_available": ONNX_AVAILABLE,
            "execution_providers": providers,
            "model_format": "onnx",
            "model_path": self.model_path,
            "model_exists": Path(self.model_path).exists(),
        }

    def _build_model_inputs(
        self,
        input_ids: np.ndarray,
        attention_mask: np.ndarray | None,
    ) -> dict[str, np.ndarray]:
        inputs: dict[str, np.ndarray] = {}
        for input_meta in self._session.get_inputs():
            name = input_meta.name
            lname = name.lower()
            if "input_ids" in lname:
                inputs[name] = input_ids
            elif "attention_mask" in lname:
                if attention_mask is None:
                    attention_mask = np.ones_like(input_ids, dtype=np.int64)
                inputs[name] = attention_mask
            elif "position_ids" in lname:
                seq_len = input_ids.shape[-1]
                position_ids = np.arange(seq_len, dtype=np.int64).reshape(1, -1)
                inputs[name] = position_ids

        if not inputs:
            first_input_name = self._session.get_inputs()[0].name
            inputs[first_input_name] = input_ids
        return inputs

    @staticmethod
    def _extract_next_token_id(model_output: Any) -> int | None:
        output = np.asarray(model_output)
        if output.size == 0:
            return None

        if np.issubdtype(output.dtype, np.integer):
            if output.ndim == 1:
                return int(output[-1])
            if output.ndim >= 2:
                return int(output.reshape(output.shape[0], -1)[0, -1])
            return int(output.item())

        if output.ndim >= 3:
            return int(np.argmax(output[0, -1, :]))
        if output.ndim == 2:
            return int(np.argmax(output[-1, :]))
        if output.ndim == 1:
            return int(np.argmax(output))
        return int(np.argmax(output))

    @staticmethod
    def _error_result(message: str) -> dict[str, Any]:
        return {
            "response": f"[ERROR] {message}",
            "tokens_generated": 0,
            "prompt_tokens": 0,
            "latency_ms": 0.0,
            "tokens_per_second": 0.0,
        }
