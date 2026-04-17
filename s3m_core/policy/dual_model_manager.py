"""Dual-model management for controlled and evaluation S3M variants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Any, Callable, Mapping


class EvalContext(str, Enum):
    """Execution context used to enforce deployment-safe model routing."""

    PRODUCTION = "PRODUCTION"
    CAPABILITY_EVAL = "CAPABILITY_EVAL"
    RED_TEAM = "RED_TEAM"
    TRAINING = "TRAINING"


class ModelVariant(str, Enum):
    """Model variant selector for training and internal control flow."""

    RAW = "RAW"
    CONTROLLED = "CONTROLLED"


@dataclass(frozen=True)
class ManagedModelHandle:
    """Local model descriptor for secure, offline tactical deployments."""

    model_path: str
    device: str
    variant: ModelVariant


MonitoringHook = Callable[[str, Mapping[str, Any]], None]


@dataclass(frozen=True)
class RedTeamMonitoredModel:
    """Wrapper that adds red-team telemetry around raw-model execution."""

    base_model: Any
    monitoring_hooks: tuple[MonitoringHook, ...]

    def emit_monitoring_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        """Emit structured monitoring telemetry to every registered hook."""
        for hook in self.monitoring_hooks:
            hook(event_type, payload)


class DualModelManager:
    """Manage raw/controlled variants with a hard production safety gate."""

    def __init__(
        self,
        raw_model_path: str,
        controlled_model_path: str,
        device: str = "cuda",
    ) -> None:
        self._raw_model_path = self._validate_local_path(raw_model_path, "raw_model_path")
        self._controlled_model_path = self._validate_local_path(
            controlled_model_path, "controlled_model_path"
        )
        if not device.strip():
            raise ValueError("device must be a non-empty string")

        self._device = device.strip()
        self._raw_model: Any | None = None
        self._controlled_model: Any | None = None
        self._active_context: EvalContext | None = None
        self._training_target: ModelVariant = ModelVariant.CONTROLLED
        self._red_team_hooks: list[MonitoringHook] = [self._default_red_team_monitor]

    def get_raw_model(self) -> Any:
        """Return raw model for eval contexts; blocked when context is production."""
        if self._is_production_locked():
            raise PermissionError(
                "Raw model access is blocked in PRODUCTION context by hard policy gate."
            )
        if self._raw_model is None:
            self._raw_model = self._load_model(self._raw_model_path, ModelVariant.RAW)
        return self._raw_model

    def get_controlled_model(self) -> Any:
        """Return policy-constrained model for mission deployment contexts."""
        if self._controlled_model is None:
            self._controlled_model = self._load_model(
                self._controlled_model_path, ModelVariant.CONTROLLED
            )
        return self._controlled_model

    def get_model_for_context(self, context: EvalContext) -> Any:
        """Resolve model handle while enforcing strict context-sensitive policy."""
        resolved_context = self._resolve_context(context)
        self._active_context = resolved_context

        if resolved_context is EvalContext.PRODUCTION:
            return self.get_controlled_model()
        if resolved_context is EvalContext.CAPABILITY_EVAL:
            return self.get_raw_model()
        if resolved_context is EvalContext.RED_TEAM:
            return RedTeamMonitoredModel(
                base_model=self.get_raw_model(),
                monitoring_hooks=tuple(self._red_team_hooks),
            )
        if resolved_context is EvalContext.TRAINING:
            if self._training_target is ModelVariant.RAW:
                return self.get_raw_model()
            return self.get_controlled_model()
        raise ValueError(f"Unsupported eval context: {context}")

    def set_training_target(self, variant: ModelVariant) -> None:
        """Set which model variant training context should return."""
        self._training_target = self._resolve_variant(variant)

    def register_red_team_hook(self, hook: MonitoringHook) -> None:
        """Register additional red-team monitoring hook for telemetry capture."""
        if not callable(hook):
            raise TypeError("hook must be callable")
        self._red_team_hooks.append(hook)

    @property
    def active_context(self) -> EvalContext | None:
        """Return the latest context used for model resolution."""
        return self._active_context

    def _load_model(self, model_path: str, variant: ModelVariant) -> Any:
        """Load local model metadata/handle in an offline-safe manner."""
        # Tactical deployments may bind this handle to an actual local runtime later.
        return ManagedModelHandle(model_path=model_path, device=self._device, variant=variant)

    @staticmethod
    def _validate_local_path(path_value: str, field_name: str) -> str:
        candidate = path_value.strip()
        if not candidate:
            raise ValueError(f"{field_name} must be a non-empty local path")
        lowered = candidate.lower()
        if lowered.startswith("http://") or lowered.startswith("https://"):
            raise ValueError(f"{field_name} must reference a local offline path")
        if "\n" in candidate or "\r" in candidate:
            raise ValueError(f"{field_name} contains invalid control characters")
        return str(Path(candidate))

    @staticmethod
    def _default_red_team_monitor(event_type: str, payload: Mapping[str, Any]) -> None:
        del event_type, payload
        return None

    @staticmethod
    def _resolve_context(context: EvalContext | str) -> EvalContext:
        if isinstance(context, EvalContext):
            return context
        if isinstance(context, str):
            try:
                return EvalContext[context.strip().upper()]
            except KeyError as exc:
                raise ValueError(f"Unknown eval context: {context}") from exc
        raise TypeError("context must be EvalContext or str")

    @staticmethod
    def _resolve_variant(variant: ModelVariant | str) -> ModelVariant:
        if isinstance(variant, ModelVariant):
            return variant
        if isinstance(variant, str):
            try:
                return ModelVariant[variant.strip().upper()]
            except KeyError as exc:
                raise ValueError(f"Unknown model variant: {variant}") from exc
        raise TypeError("variant must be ModelVariant or str")

    def _is_production_locked(self) -> bool:
        if self._active_context is EvalContext.PRODUCTION:
            return True
        runtime_context = os.getenv("S3M_RUNTIME_CONTEXT", "").strip().upper()
        return runtime_context == EvalContext.PRODUCTION.value
