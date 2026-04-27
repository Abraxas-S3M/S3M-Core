"""Real CPU training backend for cloud adaptation loops.

Military/tactical context:
This backend keeps all adaptation on CPU-only nodes so tactical retraining can
continue in disconnected environments where no accelerator is available.
"""

from __future__ import annotations

from dataclasses import asdict
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.edge_runtime.hardware_profiler import HardwareProfiler
from src.training.cloud_cpu.contracts import TrainingExample
from src.training.cpu_adaptation.adapter_tuner import AdapterConfig, CPUAdapterTuner
from src.training.cpu_adaptation.checkpointing import (
    CheckpointManifest,
    CheckpointPolicy,
    HierarchicalCheckpointer,
)
from src.training.cpu_adaptation.precision_policy import PrecisionPolicyEngine, TrainingPrecision
from src.training.cpu_adaptation.quantization import QuantAwareAdamW

try:  # Optional runtime dependency.
    import torch

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency guard
    torch = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False

try:  # Optional export dependency.
    from safetensors.torch import save_file as safetensors_save_file

    SAFETENSORS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency guard
    safetensors_save_file = None  # type: ignore[assignment]
    SAFETENSORS_AVAILABLE = False

logger = logging.getLogger("s3m.training.cloud_cpu.real_backend")


class RealCPUTrainingBackend:
    """CPU-only LoRA/QAT backend implementing the TrainingBackend protocol."""

    def __init__(
        self,
        track: str = "shared",
        base_model_path: str = "",
        checkpoint_root: Path | str = Path("state/training/cloud_cpu/real_backend"),
        adapter_config: Optional[AdapterConfig] = None,
    ) -> None:
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError(
                "RealCPUTrainingBackend requires torch, but torch is not available in this runtime."
            )

        self._track = str(track or "shared")
        self._step = 0
        self._epoch = 0
        self._last_loss = 0.0
        self._pending_backward = False
        self._latest_manifest: Optional[CheckpointManifest] = None
        self._base_model_path = str(base_model_path or "")

        profile = HardwareProfiler().run()
        self._precision_policy = PrecisionPolicyEngine(profile)
        self._qat_precision = self._precision_policy.select_precision(task_type="qat_4bit")
        self._mixed_precision = self._precision_policy.select_precision(task_type="adapter_tuning")
        self._apply_cpu_environment_recommendations()

        self._adapter_config = self._build_adapter_config(adapter_config)
        self._tuner = CPUAdapterTuner(
            base_model_path=self._base_model_path,
            config=self._adapter_config,
            precision_config=self._mixed_precision,
        )
        if not self._tuner.prepare():
            raise RuntimeError("RealCPUTrainingBackend failed to prepare CPUAdapterTuner on CPU-only path.")
        if self._tuner.model is None:
            raise RuntimeError("RealCPUTrainingBackend did not initialize a trainable model.")
        if self._tuner.optimizer is None:
            raise RuntimeError("RealCPUTrainingBackend did not initialize an optimizer.")
        if not isinstance(self._tuner.optimizer, QuantAwareAdamW):
            # Tactical guardrail: enforce the tanh-clipped QAT optimizer regardless
            # of fallback model internals so low-bit updates remain stable on CPU.
            trainable = [param for param in self._tuner.model.parameters() if param.requires_grad]
            self._tuner.optimizer = QuantAwareAdamW(
                trainable,
                lr=self._adapter_config.learning_rate,
                weight_decay=self._adapter_config.weight_decay,
                gradient_clip_norm=self._adapter_config.gradient_clip_norm,
                tanh_scale=self._adapter_config.tanh_scale,
            )

        checkpoint_root_path = Path(checkpoint_root)
        policy = CheckpointPolicy(
            l1_every_n_steps=1,
            l2_every_n_l1=0,
            l3_every_n_l2=0,
            max_l1_checkpoints=3,
            max_l2_checkpoints=0,
            checkpoint_dir=str(checkpoint_root_path / self._track),
            use_atomic_writes=True,
            verify_after_write=True,
        )
        self._checkpointer = HierarchicalCheckpointer(
            model_id=f"{self._track}-real-cpu",
            policy=policy,
            base_dir=".",
        )

    def _apply_cpu_environment_recommendations(self) -> None:
        recommendations = self._precision_policy.get_environment_recommendations()
        for key in ("OMP_NUM_THREADS", "KMP_AFFINITY", "KMP_BLOCKTIME"):
            value = recommendations.get(key)
            if isinstance(value, str) and value:
                os.environ.setdefault(key, value)

    def _build_adapter_config(self, override: Optional[AdapterConfig]) -> AdapterConfig:
        config = override or AdapterConfig()
        config.use_qat = True
        config.qat_bits = 4
        config.tanh_clipping = True
        config.tanh_scale = float(self._qat_precision.tanh_clipping_scale or 3.0)
        config.gradient_clip_norm = float(self._qat_precision.gradient_clip_norm or 0.5)
        config.use_bf16 = self._mixed_precision.training_precision is TrainingPrecision.BF16_MIXED
        return config

    @staticmethod
    def _to_tuner_sample(example: TrainingExample) -> Dict[str, str]:
        prompt = str(example.prompt)
        completion = str(example.completion)
        metadata = example.metadata if isinstance(example.metadata, dict) else {}
        instruction = str(metadata.get("instruction", prompt))
        user_input = str(metadata.get("input", ""))
        return {
            "instruction": instruction,
            "input": user_input,
            "output": completion,
            "prompt": prompt,
            "response": completion,
        }

    def forward_and_loss(self, examples: List[TrainingExample]) -> float:
        if not examples:
            return float(self._last_loss)
        if self._tuner.model is None or self._tuner.optimizer is None:
            raise RuntimeError("RealCPUTrainingBackend is not initialized with model/optimizer state.")

        self._tuner.optimizer.zero_grad(set_to_none=True)
        weighted_losses: List[torch.Tensor] = []
        total_weight = 0.0

        for example in examples:
            weight = max(0.0, float(example.weight))
            if weight <= 0.0:
                continue
            sample = self._to_tuner_sample(example)
            with self._tuner._autocast_context():
                loss_tensor = self._tuner._compute_loss_for_sample(sample)
            weighted_losses.append(loss_tensor * weight)
            total_weight += weight

        if not weighted_losses or total_weight <= 0.0:
            return float(self._last_loss)

        batch_loss = torch.stack(weighted_losses).sum() / float(total_weight)
        batch_loss.backward()
        self._pending_backward = True
        self._last_loss = float(batch_loss.detach().cpu().item())
        return self._last_loss

    def step(self, loss: float) -> None:
        if self._tuner.optimizer is None:
            raise RuntimeError("RealCPUTrainingBackend optimizer is unavailable.")
        if not self._pending_backward:
            return

        self._tuner.optimizer.step()
        self._tuner.optimizer.zero_grad(set_to_none=True)
        self._pending_backward = False
        self._step += 1
        self._epoch = self._step
        self._last_loss = float(loss)
        self._tuner._enforce_memory_budget()
        self._latest_manifest = self._save_checkpoint()

    def _adapter_state_dict(self) -> Dict[str, Any]:
        if self._tuner.model is None:
            return {}
        trainable_names = {
            name for name, parameter in self._tuner.model.named_parameters() if bool(parameter.requires_grad)
        }
        state = self._tuner.model.state_dict()
        if not trainable_names:
            return {name: tensor.detach().cpu() for name, tensor in state.items()}
        return {
            name: tensor.detach().cpu()
            for name, tensor in state.items()
            if name in trainable_names
        }

    def _save_checkpoint(self) -> Optional[CheckpointManifest]:
        if self._tuner.optimizer is None:
            return None
        try:
            return self._checkpointer.save_checkpoint(
                step=self._step,
                epoch=self._epoch,
                loss=float(self._last_loss),
                model_state=self._adapter_state_dict(),
                optimizer_state=self._tuner.optimizer.state_dict(),
                extra_metadata={
                    "track": self._track,
                    "adapter_config": asdict(self._adapter_config),
                    "precision_used": self._mixed_precision.training_precision.value,
                    "peak_memory_mb": float(self._tuner.peak_memory_mb),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive persistence path
            logger.warning("Unable to persist real CPU checkpoint at step=%s: %s", self._step, exc)
            return None

    @staticmethod
    def _manifest_from_dict(payload: Dict[str, Any]) -> CheckpointManifest:
        return CheckpointManifest(
            checkpoint_id=str(payload.get("checkpoint_id", "")),
            step=int(payload.get("step", 0)),
            epoch=int(payload.get("epoch", 0)),
            loss=float(payload.get("loss", 0.0)),
            timestamp=str(payload.get("timestamp", "")),
            level=int(payload.get("level", 1)),
            path=str(payload.get("path", "")),
            sha256=str(payload.get("sha256", "")),
            model_id=str(payload.get("model_id", "")),
            adapter_config_hash=str(payload.get("adapter_config_hash", "")),
            precision_used=str(payload.get("precision_used", "fp32")),
            peak_memory_mb=float(payload.get("peak_memory_mb", 0.0)),
            is_complete=bool(payload.get("is_complete", True)),
        )

    def get_state_dict(self) -> Dict[str, Any]:
        if self._latest_manifest is None:
            self._latest_manifest = self._save_checkpoint()
        return {
            "backend": "real_cpu_training_backend",
            "track": self._track,
            "step": int(self._step),
            "epoch": int(self._epoch),
            "last_loss": float(self._last_loss),
            "precision": self._mixed_precision.training_precision.value,
            "checkpoint_manifest": asdict(self._latest_manifest) if self._latest_manifest is not None else None,
        }

    def load_state_dict(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            raise TypeError("RealCPUTrainingBackend state must be a dictionary.")
        if self._tuner.model is None or self._tuner.optimizer is None:
            raise RuntimeError("RealCPUTrainingBackend is missing model/optimizer during restore.")

        self._step = int(state.get("step", 0))
        self._epoch = int(state.get("epoch", self._step))
        self._last_loss = float(state.get("last_loss", 0.0))
        manifest_payload = state.get("checkpoint_manifest")
        if not isinstance(manifest_payload, dict):
            return

        manifest = self._manifest_from_dict(manifest_payload)
        if not manifest.path:
            return
        checkpoint_path = Path(manifest.path)
        if not checkpoint_path.exists():
            logger.warning("RealCPUTrainingBackend checkpoint path not found during restore: %s", checkpoint_path)
            return
        loaded_payload = self._checkpointer.load_checkpoint(manifest)
        model_state = loaded_payload.get("model_state")
        optimizer_state = loaded_payload.get("optimizer_state")
        if isinstance(model_state, dict):
            self._tuner.model.load_state_dict(model_state, strict=False)
        if isinstance(optimizer_state, dict):
            self._tuner.optimizer.load_state_dict(optimizer_state)
        self._latest_manifest = manifest

    def export_adapter(self, output_path: Path | str) -> str:
        """Export LoRA adapter parameters as .pt or .safetensors."""
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required for adapter export.")
        target = Path(output_path)
        if target.suffix.lower() not in {".pt", ".safetensors"}:
            target = target.with_suffix(".pt")
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = self._adapter_state_dict()
        if target.suffix.lower() == ".safetensors":
            if not SAFETENSORS_AVAILABLE or safetensors_save_file is None:
                raise RuntimeError(
                    "safetensors export requested, but safetensors is not installed in this runtime."
                )
            safetensors_save_file(payload, str(target))
            return str(target)

        torch.save(payload, str(target))
        return str(target)
