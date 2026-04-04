"""Teacher-student distillation pipeline for CPU-only edge adaptation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from src.training.cpu_adaptation.adapter_tuner import AdapterConfig, CPUAdapterTuner

logger = logging.getLogger("s3m.training.distillation_engine")


class InferenceBackend(Protocol):
    """Protocol for local teacher backends used in distillation."""

    def generate(self, prompt: str, **kwargs: Any) -> Any:
        """Run local inference for a single prompt."""


@dataclass
class DistillResult:
    """Result of CPU distillation from teacher outputs to student artifact."""

    student_path: str
    samples_used: int
    teacher_agreement_pct: float
    duration_sec: float


class DistillationEngine:
    """Distills larger local models into smaller edge-deployable students.

    Military/tactical context:
    Distillation lets command systems shrink model footprints before deployment
    so platoon-grade compute nodes can continue autonomous operation when cloud
    backhaul is denied or unavailable.
    """

    def __init__(self, teacher_backend: InferenceBackend, student_config: dict) -> None:
        if teacher_backend is None:
            raise ValueError("teacher_backend must not be None")
        if not isinstance(student_config, dict):
            raise ValueError("student_config must be a dictionary")
        self.teacher_backend = teacher_backend
        self.student_config = student_config

    @staticmethod
    def _extract_text(payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            if "response" in payload and isinstance(payload["response"], str):
                return payload["response"].strip()
            if "text" in payload and isinstance(payload["text"], str):
                return payload["text"].strip()
        if hasattr(payload, "response"):
            val = getattr(payload, "response")
            if isinstance(val, str):
                return val.strip()
        return str(payload).strip()

    def generate_training_data(self, prompts: list[str], max_samples: int = 1000) -> list[dict]:
        """Query teacher backend and build distillation supervision pairs."""
        if not isinstance(prompts, list):
            raise ValueError("prompts must be a list of strings")
        if int(max_samples) <= 0:
            raise ValueError("max_samples must be > 0")

        pairs: list[dict] = []
        for prompt in prompts[: int(max_samples)]:
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            try:
                result = self.teacher_backend.generate(prompt)
                teacher_response = self._extract_text(result)
                if not teacher_response:
                    continue
                pairs.append(
                    {
                        "instruction": prompt,
                        "input": "",
                        "output": teacher_response,
                        "prompt": prompt,
                        "teacher_response": teacher_response,
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Teacher generation failed for prompt: %s", exc)
        return pairs

    def _build_adapter_config(self) -> AdapterConfig:
        cfg = self.student_config.get("adapter_config", {})
        if not isinstance(cfg, dict):
            cfg = {}
        return AdapterConfig(
            lora_rank=int(cfg.get("lora_rank", 8)),
            lora_alpha=int(cfg.get("lora_alpha", 16)),
            target_modules=list(cfg.get("target_modules", ["q_proj", "v_proj"])),
            learning_rate=float(cfg.get("learning_rate", 2e-4)),
            max_steps=int(cfg.get("max_steps", 200)),
            batch_size=int(cfg.get("batch_size", 1)),
            gradient_accumulation_steps=int(cfg.get("gradient_accumulation_steps", 4)),
            max_memory_mb=int(cfg.get("max_memory_mb", 4096)),
        )

    def _estimate_agreement(
        self,
        training_data: list[dict],
        loss_history: list[float],
    ) -> float:
        student_backend = self.student_config.get("student_backend")
        if student_backend is not None and hasattr(student_backend, "generate"):
            compared = 0
            score = 0.0
            for row in training_data[:25]:
                prompt = str(row.get("prompt", row.get("instruction", ""))).strip()
                teacher = str(row.get("teacher_response", row.get("output", ""))).strip()
                if not prompt or not teacher:
                    continue
                try:
                    student_out = self._extract_text(student_backend.generate(prompt))
                except Exception:
                    continue
                teacher_tokens = set(teacher.split())
                student_tokens = set(student_out.split())
                if not teacher_tokens:
                    continue
                overlap = len(teacher_tokens.intersection(student_tokens)) / float(len(teacher_tokens))
                score += overlap
                compared += 1
            if compared > 0:
                return max(0.0, min(100.0, (score / compared) * 100.0))

        if not loss_history:
            return 0.0
        avg_loss = float(sum(loss_history) / len(loss_history))
        proxy = 100.0 / (1.0 + max(0.0, avg_loss))
        return max(0.0, min(100.0, proxy))

    def distill(self, training_data: list[dict], student_model_path: str) -> DistillResult:
        """Fine-tune student artifact from teacher outputs using CPUAdapterTuner."""
        if not isinstance(training_data, list) or not training_data:
            raise ValueError("training_data must be a non-empty list of dictionaries")
        if not isinstance(student_model_path, str) or not student_model_path.strip():
            raise ValueError("student_model_path must be a non-empty string")

        start = time.perf_counter()
        base_model_path = str(self.student_config.get("base_model_path", student_model_path))
        adapter_cfg = self._build_adapter_config()
        tuner = CPUAdapterTuner(base_model_path=base_model_path, adapter_config=adapter_cfg)

        if not tuner.prepare():
            raise RuntimeError("Failed to prepare CPUAdapterTuner for distillation")

        train_result = tuner.train(training_data)
        quant_format = str(self.student_config.get("quant_format", "q4_k_m"))
        merge = bool(self.student_config.get("merge_and_quantize", True))
        if merge:
            student_path = tuner.merge_and_quantize(student_model_path, quant_format=quant_format)
        else:
            student_path = tuner.export_adapter(student_model_path)

        agreement = self._estimate_agreement(training_data, train_result.loss_history)
        duration = time.perf_counter() - start
        return DistillResult(
            student_path=student_path,
            samples_used=len(training_data),
            teacher_agreement_pct=agreement,
            duration_sec=duration,
        )
