"""
S3M OpenVINO Backend
Supports OpenVINO IR execution for air-gapped tactical inference on CPU-first hardware.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any
import logging

import numpy as np

from .base_backend import InferenceBackend

try:
    from openvino.runtime import Core

    OPENVINO_AVAILABLE = True
except ImportError:
    Core = None
    OPENVINO_AVAILABLE = False

try:
    from optimum.intel import OVModelForCausalLM

    OPTIMUM_OPENVINO_AVAILABLE = True
except ImportError:
    OVModelForCausalLM = None
    OPTIMUM_OPENVINO_AVAILABLE = False

try:
    from transformers import AutoTokenizer

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    AutoTokenizer = None
    TRANSFORMERS_AVAILABLE = False

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

logger = logging.getLogger("s3m.backends.openvino")


class OpenVinoBackend(InferenceBackend):
    """Inference backend for OpenVINO IR models."""

    def __init__(self, model_path: str, config: dict[str, Any]) -> None:
        super().__init__(model_path=model_path, config=config)
        self.device = str(config.get("device", "CPU"))
        self.num_streams = config.get("num_streams")
        self.inference_precision = config.get("inference_precision")

        self._core: Any = None
        self._compiled_model: Any = None
        self._ov_model: Any = None
        self._tokenizer: Any = None
        self._model_xml_path: Path | None = None

    @property
    def backend_name(self) -> str:
        return "openvino"

    def load(self) -> bool:
        if not TRANSFORMERS_AVAILABLE or AutoTokenizer is None:
            logger.warning("transformers is not installed; tokenizer load unavailable")
            return False

        model_path_obj = Path(self.model_path)
        tokenizer_path = self.config.get("tokenizer_path") or (
            str(model_path_obj.parent) if model_path_obj.is_file() else str(model_path_obj)
        )

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                tokenizer_path,
                local_files_only=True,
            )
        except Exception:
            logger.exception("Failed to load tokenizer for OpenVINO backend")
            return False

        if OPTIMUM_OPENVINO_AVAILABLE and OVModelForCausalLM is not None:
            try:
                model_source = str(model_path_obj.parent if model_path_obj.is_file() else model_path_obj)
                self._ov_model = OVModelForCausalLM.from_pretrained(
                    model_source,
                    device=self.device,
                    local_files_only=True,
                    compile=False,
                )
                self._ov_model.compile()
                self._loaded = True
                return True
            except Exception:
                logger.warning("Optimum OpenVINO path unavailable, trying raw Core API", exc_info=True)
                self._ov_model = None

        if not OPENVINO_AVAILABLE or Core is None:
            logger.warning("openvino.runtime is not installed; backend unavailable")
            return False

        model_xml_path = self._resolve_model_xml(model_path_obj)
        if model_xml_path is None:
            logger.error("OpenVINO IR XML model not found at: %s", self.model_path)
            return False

        compile_config: dict[str, str] = {}
        if self.num_streams is not None:
            compile_config["NUM_STREAMS"] = str(self.num_streams)
        if self.inference_precision is not None:
            compile_config["INFERENCE_PRECISION_HINT"] = str(self.inference_precision)

        try:
            self._core = Core()
            self._compiled_model = self._core.compile_model(
                model=str(model_xml_path),
                device_name=self.device,
                config=compile_config,
            )
            self._model_xml_path = model_xml_path
            self._loaded = True
            return True
        except Exception:
            logger.exception("Failed to compile OpenVINO model")
            self._compiled_model = None
            self._loaded = False
            return False

    def unload(self) -> None:
        self._compiled_model = None
        self._core = None
        self._ov_model = None
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
        if not self._loaded or self._tokenizer is None:
            return self._error_result("Model not loaded")

        if self._ov_model is not None and TORCH_AVAILABLE and torch is not None:
            try:
                return self._generate_with_optimum(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop=stop,
                )
            except Exception:
                logger.warning("Optimum generation failed, falling back to raw path", exc_info=True)

        if self._compiled_model is None:
            return self._error_result("No runnable OpenVINO model instance")

        return self._generate_with_raw_core(
            prompt=prompt,
            max_tokens=max_tokens,
            stop=stop,
        )

    def health_check(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "loaded": self._loaded,
            "openvino_available": OPENVINO_AVAILABLE,
            "device": self.device,
            "num_streams": self.num_streams,
            "model_format": "openvino",
            "optimum_openvino_available": OPTIMUM_OPENVINO_AVAILABLE,
            "model_path": self.model_path,
            "model_exists": Path(self.model_path).exists(),
        }

    def _generate_with_optimum(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop: list[str] | None,
    ) -> dict[str, Any]:
        assert torch is not None
        start = perf_counter()
        encoded = self._tokenizer(prompt, return_tensors="pt")
        input_ids = encoded["input_ids"]
        attention_mask = encoded.get("attention_mask")
        prompt_tokens = int(input_ids.shape[-1])

        generated = self._ov_model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_tokens,
            do_sample=temperature > 0,
            temperature=temperature,
            top_p=top_p,
        )

        response_ids = generated[0, prompt_tokens:]
        response_text = self._tokenizer.decode(response_ids, skip_special_tokens=True).strip()
        if stop:
            for marker in stop:
                if marker and marker in response_text:
                    response_text = response_text.split(marker, 1)[0].rstrip()

        latency_ms = (perf_counter() - start) * 1000.0
        tokens_generated = int(response_ids.shape[-1])
        tokens_per_second = (tokens_generated / (latency_ms / 1000.0)) if latency_ms > 0 else 0.0

        return {
            "response": response_text,
            "tokens_generated": tokens_generated,
            "prompt_tokens": prompt_tokens,
            "latency_ms": latency_ms,
            "tokens_per_second": tokens_per_second,
        }

    def _generate_with_raw_core(
        self,
        prompt: str,
        max_tokens: int,
        stop: list[str] | None,
    ) -> dict[str, Any]:
        start = perf_counter()
        encoded = self._tokenizer(prompt, return_tensors="np")
        generated_ids = encoded["input_ids"].astype(np.int64)
        attention_mask = encoded.get("attention_mask")
        if attention_mask is not None:
            attention_mask = attention_mask.astype(np.int64)

        initial_tokens = int(generated_ids.shape[-1])

        for _ in range(max_tokens):
            model_inputs = self._build_model_inputs(generated_ids, attention_mask)
            infer_result = self._compiled_model(model_inputs)
            first_output = next(iter(infer_result.values()))
            next_token = self._extract_next_token_id(first_output)
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
            "prompt_tokens": initial_tokens,
            "latency_ms": latency_ms,
            "tokens_per_second": tokens_per_second,
        }

    def _build_model_inputs(
        self,
        input_ids: np.ndarray,
        attention_mask: np.ndarray | None,
    ) -> dict[str, np.ndarray]:
        inputs: dict[str, np.ndarray] = {}
        for input_port in self._compiled_model.inputs:
            name = input_port.get_any_name()
            lname = name.lower()
            if "input_ids" in lname:
                inputs[name] = input_ids
            elif "attention_mask" in lname:
                if attention_mask is None:
                    attention_mask = np.ones_like(input_ids, dtype=np.int64)
                inputs[name] = attention_mask
            elif "position_ids" in lname:
                seq_len = input_ids.shape[-1]
                inputs[name] = np.arange(seq_len, dtype=np.int64).reshape(1, -1)

        if not inputs:
            inputs[self._compiled_model.inputs[0].get_any_name()] = input_ids
        return inputs

    @staticmethod
    def _resolve_model_xml(model_path_obj: Path) -> Path | None:
        if model_path_obj.is_file() and model_path_obj.suffix.lower() == ".xml":
            return model_path_obj
        if model_path_obj.is_dir():
            xml_files = sorted(model_path_obj.glob("*.xml"))
            return xml_files[0] if xml_files else None
        return None

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
