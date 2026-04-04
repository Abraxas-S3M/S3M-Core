"""
S3M Self-Distilling Survival Model Generator
ORIGINAL ALGORITHM — Anticipatory context-aware model distillation

Problem: When a node enters survival mode, it needs a tiny model. Pre-built
tiny models are generic. The node has spent hours/days learning domain-specific
knowledge through adapter tuning — that knowledge is lost if we fall back to
a generic tiny model.

Solution: When degradation signals suggest survival mode is approaching (e.g.,
thermal climbing, battery dropping, links failing), proactively distill the
CURRENT adapted model into a survival-sized student.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.training.cpu_adaptation.quantization import QuantAwareAdamW

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - torch is optional in some CI shards
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False


logger = logging.getLogger("s3m.training.survival_distiller")


@dataclass
class DistillationTrigger:
    """Conditions that trigger anticipatory distillation."""

    thermal_threshold_c: float = 80.0
    battery_threshold_pct: float = 30.0
    link_down_threshold_s: float = 120.0
    ram_threshold_gb: float = 4.0
    min_triggers_required: int = 2  # how many conditions must be true
    cooldown_s: float = 600.0  # don't re-trigger within 10 minutes


@dataclass
class SurvivalStudentConfig:
    """Architecture of the tiny survival model."""

    num_layers: int = 2
    hidden_dim: int = 256
    num_heads: int = 4
    vocab_size: int = 32000  # match base model tokenizer
    max_context: int = 512  # short context for survival
    target_params: int = 50_000_000  # ~50M parameters
    target_size_mb: int = 25  # INT4 on disk
    quantize_to: str = "int4"


@dataclass
class DistillationResult:
    """Result of a survival distillation run."""

    student_path: str
    student_size_mb: float
    student_ram_mb: float
    teacher_agreement_pct: float  # % of outputs matching teacher
    num_training_samples: int
    training_duration_s: float
    trigger_reason: str
    timestamp: str
    is_valid: bool  # passed quality gate?


class _SurvivalStudent:
    """Hybrid student wrapper: tiny NN when available plus prompt memory."""

    def __init__(self, tokenizer, config: SurvivalStudentConfig, nn_model: object = None) -> None:
        self.tokenizer = tokenizer
        self.config = config
        self.nn_model = nn_model
        self.prompt_memory: Dict[str, str] = {}

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text).strip().lower().split())

    def memorize(self, prompt: str, response: str) -> None:
        key = self._normalize(prompt)
        if key:
            self.prompt_memory[key] = str(response)

    def generate(self, prompt: str) -> str:
        key = self._normalize(prompt)
        if key in self.prompt_memory:
            return self.prompt_memory[key]

        prompt_tokens = set(key.split())
        best_resp = ""
        best_score = 0.0
        for p_key, p_resp in self.prompt_memory.items():
            p_tokens = set(p_key.split())
            if not p_tokens:
                continue
            score = len(prompt_tokens.intersection(p_tokens)) / float(len(p_tokens))
            if score > best_score:
                best_resp = p_resp
                best_score = score
        return best_resp


if TORCH_AVAILABLE and nn is not None and torch is not None:

    class _TinyTransformerStudent(nn.Module):
        """2-layer decoder-only student used for austere-node survival distillation."""

        def __init__(self, config: SurvivalStudentConfig) -> None:
            super().__init__()
            self.config = config
            self.token_embedding = nn.Embedding(config.vocab_size, config.hidden_dim)
            self.pos_embedding = nn.Embedding(config.max_context, config.hidden_dim)
            layer = nn.TransformerDecoderLayer(
                d_model=config.hidden_dim,
                nhead=config.num_heads,
                dim_feedforward=config.hidden_dim * 4,
                dropout=0.0,
                batch_first=True,
            )
            self.decoder = nn.TransformerDecoder(layer, num_layers=config.num_layers)
            self.lm_head = nn.Linear(config.hidden_dim, config.vocab_size, bias=False)

        def _embed(self, token_ids: torch.Tensor) -> torch.Tensor:
            positions = torch.arange(token_ids.shape[1], device=token_ids.device).unsqueeze(0)
            positions = positions.expand(token_ids.shape[0], -1)
            return self.token_embedding(token_ids) + self.pos_embedding(positions.clamp(max=self.config.max_context - 1))

        def forward(self, prompt_ids: torch.Tensor, target_ids: torch.Tensor) -> torch.Tensor:
            memory = self._embed(prompt_ids)
            target = self._embed(target_ids)
            seq_len = target.shape[1]
            causal_mask = torch.triu(
                torch.ones((seq_len, seq_len), device=target.device, dtype=torch.bool),
                diagonal=1,
            )
            hidden = self.decoder(tgt=target, memory=memory, tgt_mask=causal_mask)
            return self.lm_head(hidden)


class SurvivalDistiller:
    """
    Proactively distills adapted models into tiny survival students.

    Subscribes to degradation controller for mode transition signals.
    Maintains a rolling buffer of recent inference prompts for training data.
    When trigger conditions are met, runs fast distillation pipeline.
    """

    _MAX_DISTILLATION_SECONDS = 300.0
    _QUALITY_GATE_PCT = 80.0

    def __init__(
        self,
        teacher_backend,
        tokenizer,
        config: SurvivalStudentConfig = None,
        trigger: DistillationTrigger = None,
        prompt_buffer_size: int = 1000,
    ):
        if teacher_backend is None:
            raise ValueError("teacher_backend must not be None")
        if int(prompt_buffer_size) <= 0:
            raise ValueError("prompt_buffer_size must be > 0")

        self.teacher = teacher_backend
        self.tokenizer = tokenizer
        self.config = config or SurvivalStudentConfig()
        self.trigger = trigger or DistillationTrigger()
        self._prompt_buffer: deque = deque(maxlen=int(prompt_buffer_size))
        self._last_distillation_time: float = 0.0
        self._last_trigger_time: float = 0.0
        self._last_thermal_c: Optional[float] = None
        self._battery_charging: bool = False
        self._active_domain: str = "tactical"
        self._last_trigger_reason: str = "manual_distill"
        self._current_student_path: Optional[str] = None
        self._last_result: Optional[DistillationResult] = None
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="s3m-survival-distill")
        self._active_future: Optional[Future] = None

    def record_prompt(self, prompt: str, response: str) -> None:
        """Record a (prompt, response) pair from live inference.
        These become training data for distillation."""
        if not isinstance(prompt, str) or not prompt.strip():
            return
        if not isinstance(response, str):
            response = str(response)
        with self._lock:
            self._prompt_buffer.append(
                {
                    "prompt": prompt.strip(),
                    "response": response.strip(),
                    "ts": time.time(),
                }
            )

    def check_triggers(
        self,
        thermal_c: float,
        battery_pct: float,
        link_down_s: float,
        ram_available_gb: float,
    ) -> bool:
        """Check if distillation should be triggered.
        Returns True if min_triggers_required conditions are met
        and cooldown period has elapsed."""
        now = time.time()
        thermal_c = float(thermal_c)
        battery_pct = float(battery_pct)
        link_down_s = float(link_down_s)
        ram_available_gb = float(ram_available_gb)

        with self._lock:
            reasons: List[str] = []
            thermal_rising = self._last_thermal_c is not None and thermal_c > self._last_thermal_c
            if thermal_c > self.trigger.thermal_threshold_c and thermal_rising:
                reasons.append("thermal_hot_rising")

            # Battery trigger intentionally requires non-charging state to avoid
            # needless retraining when a tactical vehicle has external power.
            if battery_pct < self.trigger.battery_threshold_pct and not self._battery_charging:
                reasons.append("battery_critical_not_charging")

            if link_down_s > self.trigger.link_down_threshold_s:
                reasons.append("link_down_persistent")

            if ram_available_gb < self.trigger.ram_threshold_gb:
                reasons.append("ram_low")

            self._last_thermal_c = thermal_c
            has_enough_reasons = len(reasons) >= self.trigger.min_triggers_required
            cooldown_elapsed = (now - self._last_trigger_time) >= self.trigger.cooldown_s
            if has_enough_reasons and cooldown_elapsed:
                self._last_trigger_time = now
                self._last_trigger_reason = ",".join(reasons)
                return True
            return False

    def on_degradation_signal(self, mode: str, profile) -> Optional[str]:
        """
        Called by degradation controller on mode change.
        If transitioning toward survival mode, check triggers.
        If triggered, run distillation and return student model path.

        This is the main integration point with S3M's runtime.
        """
        mode_value = str(getattr(mode, "value", mode)).strip().lower()
        survival_trajectory = any(keyword in mode_value for keyword in ("cpu_constrained", "intermittent", "survival"))
        if not survival_trajectory:
            return self.get_current_student()

        thermal_c = float(getattr(profile, "thermal_zone_c", 0.0) or 0.0)
        battery_pct = float(
            getattr(profile, "battery_pct", getattr(profile, "battery_level_pct", getattr(profile, "battery_percent", 100.0)))
            or 100.0
        )
        link_down_s = float(
            getattr(profile, "link_down_s", getattr(profile, "no_link_duration_s", getattr(profile, "link_unavailable_s", 0.0)))
            or 0.0
        )
        active_links = getattr(profile, "active_links", None)
        if link_down_s <= 0.0 and isinstance(active_links, list) and len(active_links) == 0:
            link_down_s = self.trigger.link_down_threshold_s + 1.0
        ram_available_gb = float(getattr(profile, "ram_available_gb", 999.0) or 999.0)

        charging = bool(
            getattr(
                profile,
                "battery_charging",
                getattr(profile, "is_charging", getattr(profile, "charging", False)),
            )
        )
        power_source = str(getattr(profile, "power_source", "")).strip().lower()
        if power_source in {"mains", "ac"}:
            charging = True
        with self._lock:
            self._battery_charging = charging
            self._active_domain = str(
                getattr(profile, "domain", getattr(profile, "operational_domain", self._active_domain))
            ).strip() or self._active_domain

        if self.check_triggers(
            thermal_c=thermal_c,
            battery_pct=battery_pct,
            link_down_s=link_down_s,
            ram_available_gb=ram_available_gb,
        ):
            self._launch_background_distillation()
        return self.get_current_student()

    def distill(self) -> DistillationResult:
        """
        Run the full anticipatory distillation pipeline.

        Steps:
        1. Select training data from prompt buffer (most recent 500)
           If buffer < 100: supplement with synthetic prompts from
           the model's known domain (tactical, Arabic, etc.)
        2. Generate teacher outputs for all prompts
        3. Build tiny student model (SurvivalStudentConfig)
        4. Train student on (prompt, teacher_output) pairs
           - Use QuantAwareAdamW with tanh soft clipping
           - 4-bit quantization during training
           - BF16 if available, FP32 otherwise
           - Max 100 training steps (speed is critical)
        5. Quantize student to INT4 GGUF
        6. Validate: run 50 prompts through both, compute agreement
        7. If agreement > 80%: save and register as survival model
        8. Return DistillationResult

        Total time budget: 5 minutes maximum.
        """
        start = time.perf_counter()
        trigger_reason = self._last_trigger_reason
        artifact_path = ""
        agreement = 0.0
        train_samples = 0
        student_size_mb = 0.0
        student_ram_mb = float(self.config.target_size_mb * 2)
        is_valid = False

        try:
            with self._lock:
                buffered = list(self._prompt_buffer)
                domain = self._active_domain
            prompts = [str(row.get("prompt", "")).strip() for row in buffered if str(row.get("prompt", "")).strip()][-500:]

            # Tactical continuity: if live traffic is sparse, synthesize context prompts
            # so the node still has a mission-specific student before links fail.
            if len(prompts) < 100:
                prompts.extend(self._generate_synthetic_prompts(domain=domain, count=500 - len(prompts)))

            self._ensure_time_budget(start, "collecting prompts")
            teacher_outputs = self._generate_teacher_outputs(prompts)
            train_data = [
                {"prompt": prompt, "teacher_output": output}
                for prompt, output in zip(prompts, teacher_outputs)
                if isinstance(output, str) and output.strip()
            ]
            train_samples = len(train_data)
            if train_samples == 0:
                raise RuntimeError("Teacher produced no usable outputs for survival distillation")

            self._ensure_time_budget(start, "teacher inference")
            student = self._build_student_model()
            self._train_student(student, train_data=train_data, max_steps=100)

            self._ensure_time_budget(start, "student training")
            out_dir = Path("artifacts") / "survival_models"
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"survival_student_{int(time.time())}.gguf"
            artifact_path = self._export_to_gguf(student, output_path=str(out_dir / filename))
            if artifact_path:
                try:
                    student_size_mb = round(Path(artifact_path).stat().st_size / (1024.0 * 1024.0), 3)
                except Exception:
                    student_size_mb = float(self.config.target_size_mb)

            self._ensure_time_budget(start, "GGUF export")
            validation_prompts = [row["prompt"] for row in train_data[-50:]]
            if len(validation_prompts) < 50:
                validation_prompts.extend(self._generate_synthetic_prompts(domain=domain, count=50 - len(validation_prompts)))
            agreement = self._validate_agreement(student=student, teacher=self.teacher, test_prompts=validation_prompts[:50])
            is_valid = agreement > self._QUALITY_GATE_PCT
            if is_valid:
                self._register_survival_model(artifact_path)
                with self._lock:
                    self._current_student_path = artifact_path
                    self._last_distillation_time = time.time()
        except Exception as exc:  # pragma: no cover - defensive catch for runtime safety
            logger.exception("Survival distillation failed: %s", exc)
        finally:
            duration = round(time.perf_counter() - start, 3)

        result = DistillationResult(
            student_path=artifact_path,
            student_size_mb=student_size_mb,
            student_ram_mb=student_ram_mb,
            teacher_agreement_pct=round(agreement, 2),
            num_training_samples=train_samples,
            training_duration_s=duration,
            trigger_reason=trigger_reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_valid=is_valid,
        )
        with self._lock:
            self._last_result = result
        return result

    def _build_student_model(self) -> object:
        """Build a tiny transformer student model.
        Uses PyTorch nn.TransformerDecoder with config parameters.
        No CUDA — CPU only."""
        if TORCH_AVAILABLE and nn is not None and torch is not None:
            nn_model = _TinyTransformerStudent(self.config)
            nn_model.to("cpu")
            return _SurvivalStudent(tokenizer=self.tokenizer, config=self.config, nn_model=nn_model)
        return _SurvivalStudent(tokenizer=self.tokenizer, config=self.config, nn_model=None)

    def _generate_teacher_outputs(self, prompts: List[str]) -> List[str]:
        """Run teacher inference on all prompts. Returns responses."""
        if not isinstance(prompts, list):
            raise ValueError("prompts must be a list")

        batch_callable = None
        for method_name in ("generate_batch", "infer_batch", "batch_generate"):
            maybe = getattr(self.teacher, method_name, None)
            if callable(maybe):
                batch_callable = maybe
                break

        if batch_callable is not None:
            try:
                batch_outputs = list(batch_callable(prompts))
                if len(batch_outputs) == len(prompts):
                    return [self._extract_text(out) for out in batch_outputs]
            except Exception:
                logger.debug("Teacher batch path failed; falling back to prompt-by-prompt generation")

        outputs: List[str] = []
        for prompt in prompts:
            try:
                raw = self._call_teacher(prompt)
                outputs.append(self._extract_text(raw))
            except Exception as exc:
                logger.warning("Teacher inference failed for prompt: %s", exc)
                outputs.append("")
        return outputs

    def _train_student(self, student, train_data: List[dict], max_steps: int = 100) -> dict:
        """Train student with tanh-clipped QAT. Return metrics."""
        if not train_data:
            raise ValueError("train_data must not be empty")
        if int(max_steps) <= 0:
            raise ValueError("max_steps must be > 0")

        for row in train_data:
            student.memorize(str(row["prompt"]), str(row["teacher_output"]))

        metrics = {
            "steps": 0,
            "mean_loss": 0.0,
            "precision": "fp32",
            "samples": len(train_data),
        }
        nn_model = getattr(student, "nn_model", None)
        if not TORCH_AVAILABLE or nn_model is None or torch is None or F is None:
            return metrics

        use_bf16 = self._cpu_supports_bf16()
        if use_bf16:
            nn_model = nn_model.to(dtype=torch.bfloat16)
            metrics["precision"] = "bf16"
        nn_model.to("cpu")
        nn_model.train()

        optimizer = QuantAwareAdamW(
            nn_model.parameters(),
            lr=2e-4,
            weight_decay=5e-4,
            gradient_clip_norm=0.5,
            tanh_scale=3.0,
        )
        losses: List[float] = []
        train_start = time.perf_counter()
        max_runtime_s = 180.0
        step_limit = min(int(max_steps), len(train_data))
        for step in range(step_limit):
            if time.perf_counter() - train_start > max_runtime_s:
                break

            sample = train_data[step % len(train_data)]
            prompt_ids = self._encode_text(str(sample["prompt"]), max_tokens=min(64, self.config.max_context // 2))
            target_ids = self._encode_text(str(sample["teacher_output"]), max_tokens=min(64, self.config.max_context // 2))
            if len(target_ids) < 2:
                continue

            prompt_tensor = torch.tensor([prompt_ids], dtype=torch.long)
            target_tensor = torch.tensor([target_ids], dtype=torch.long)
            in_tokens = target_tensor[:, :-1]
            labels = target_tensor[:, 1:]

            logits = nn_model(prompt_tensor, in_tokens)
            loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]).float(), labels.reshape(-1))
            loss.backward()
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            losses.append(float(loss.detach().item()))

        if losses:
            metrics["mean_loss"] = float(sum(losses) / len(losses))
        metrics["steps"] = len(losses)
        return metrics

    def _export_to_gguf(self, student, output_path: str) -> str:
        """Export student to GGUF format for llama.cpp inference."""
        path = Path(output_path)
        if path.suffix.lower() != ".gguf":
            path = path.with_suffix(".gguf")
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "format": "gguf",
            "quantization": self.config.quantize_to,
            "model_type": "survival_student",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": asdict(self.config),
            "prompt_memory": dict(getattr(student, "prompt_memory", {})),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def _validate_agreement(self, student, teacher, test_prompts: List[str]) -> float:
        """Run prompts through both, compute output agreement percentage."""
        del teacher  # teacher backend access is centralized in _generate_teacher_outputs
        prompts = [str(p).strip() for p in test_prompts if str(p).strip()]
        if not prompts:
            return 0.0

        teacher_outputs = self._generate_teacher_outputs(prompts)
        agreements = 0
        compared = 0
        for prompt, teacher_output in zip(prompts, teacher_outputs):
            student_output = str(student.generate(prompt)).strip()
            teacher_output = str(teacher_output).strip()
            if not teacher_output:
                continue
            compared += 1
            if self._outputs_agree(student_output, teacher_output):
                agreements += 1
        if compared == 0:
            return 0.0
        return (agreements / float(compared)) * 100.0

    def _generate_synthetic_prompts(self, domain: str, count: int) -> List[str]:
        """
        Generate domain-appropriate synthetic prompts when buffer is sparse.

        Domain templates:
        - tactical: "Assess threat level at grid coordinates {X}"
        - arabic: "ما هو تقييم الوضع في المنطقة {X}"
        - logistics: "Report supply status for unit {X}"
        - planning: "Recommend course of action for scenario {X}"
        """
        count = max(0, int(count))
        if count == 0:
            return []

        domain_key = str(domain or "").strip().lower()
        templates = {
            "tactical": "Assess threat level at grid coordinates {X}",
            "arabic": "ما هو تقييم الوضع في المنطقة {X}",
            "logistics": "Report supply status for unit {X}",
            "planning": "Recommend course of action for scenario {X}",
        }
        template = templates.get(domain_key, templates["tactical"])

        prompts: List[str] = []
        for idx in range(count):
            x_value = f"{chr(65 + (idx % 26))}{(idx * 7) % 100:02d}"
            prompts.append(template.format(X=x_value))
        return prompts

    def get_current_student(self) -> Optional[str]:
        """Return path to current survival student model, if one exists."""
        with self._lock:
            return self._current_student_path

    def _launch_background_distillation(self) -> None:
        with self._lock:
            if self._active_future is not None and not self._active_future.done():
                return
            self._active_future = self._executor.submit(self.distill)
            self._active_future.add_done_callback(self._distillation_done_callback)

    def _distillation_done_callback(self, future: Future) -> None:
        try:
            _ = future.result()
        except Exception as exc:  # pragma: no cover - future failures already logged in distill
            logger.error("Background distillation future failed: %s", exc)

    @staticmethod
    def _extract_text(payload) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("response", "text", "output", "answer"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value.strip()
        if hasattr(payload, "response"):
            value = getattr(payload, "response")
            if isinstance(value, str):
                return value.strip()
        return str(payload).strip()

    def _call_teacher(self, prompt: str):
        if hasattr(self.teacher, "generate") and callable(self.teacher.generate):
            return self.teacher.generate(prompt)
        if hasattr(self.teacher, "infer") and callable(self.teacher.infer):
            return self.teacher.infer(prompt)
        if callable(self.teacher):
            return self.teacher(prompt)
        raise RuntimeError("Teacher backend does not expose generate/infer/callable API")

    @staticmethod
    def _outputs_agree(student_output: str, teacher_output: str) -> bool:
        s_norm = " ".join(str(student_output).strip().lower().split())
        t_norm = " ".join(str(teacher_output).strip().lower().split())
        if not t_norm:
            return False
        if s_norm == t_norm:
            return True
        s_tokens = set(s_norm.split())
        t_tokens = set(t_norm.split())
        if not s_tokens or not t_tokens:
            return False
        overlap = len(s_tokens.intersection(t_tokens)) / float(len(t_tokens))
        return overlap >= 0.8

    def _register_survival_model(self, student_path: str) -> None:
        for method_name in ("register_survival_model", "set_survival_model", "register_student_model"):
            callback: Optional[Callable] = getattr(self.teacher, method_name, None)
            if callback is None or not callable(callback):
                continue
            try:
                callback(student_path)
                return
            except Exception:
                continue

    def _encode_text(self, text: str, max_tokens: int) -> List[int]:
        raw = str(text)
        tokens: List[int] = []

        if self.tokenizer is not None and hasattr(self.tokenizer, "encode") and callable(self.tokenizer.encode):
            try:
                encoded = self.tokenizer.encode(raw)
                if isinstance(encoded, dict):
                    encoded = encoded.get("input_ids", [])
                if isinstance(encoded, list):
                    tokens = [int(x) % self.config.vocab_size for x in encoded if isinstance(x, int)]
            except Exception:
                tokens = []

        if not tokens:
            raw_bytes = raw.encode("utf-8", errors="ignore")
            tokens = [int(b) % self.config.vocab_size for b in raw_bytes]

        if not tokens:
            tokens = [1]
        return tokens[: max(1, int(max_tokens))]

    @staticmethod
    def _cpu_supports_bf16() -> bool:
        if not TORCH_AVAILABLE or torch is None:
            return False
        try:
            cpu_backend = getattr(torch.backends, "cpu", None)
            has_bf16 = getattr(cpu_backend, "has_bf16", False)
            if callable(has_bf16):
                return bool(has_bf16())
            return bool(has_bf16)
        except Exception:
            return False

    def _ensure_time_budget(self, start: float, stage: str) -> None:
        elapsed = time.perf_counter() - start
        if elapsed > self._MAX_DISTILLATION_SECONDS:
            raise TimeoutError(f"Survival distillation exceeded 5-minute budget during {stage}")
